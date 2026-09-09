#!/usr/bin/env python3
"""Resolve exact passing artifacts and promote one owned folder without force pushes."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
import random
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from contract import ID, SHA, MAX_TOTAL, assemble, decide, digest, install, read_json, registry, require, rows, safe_name, stage, validate_state, write_json

TARGET = 'AxiomsAwake/web'
BASE_URL = 'https://axiomsawake.github.io/web/'


def api(path: str):
    token = os.environ.get('SOURCE_TOKEN', '')
    require(bool(token), 'Source GITHUB_TOKEN is required for exact-run verification')
    request = urllib.request.Request('https://api.github.com/repos/' + path, headers={
        'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'axioms-web-publisher'})
    # All API calls here return JSON; reject redirects rather than forwarding a credential.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
        data = response.read(8 * 1024 * 1024 + 1)
        require(len(data) <= 8 * 1024 * 1024, 'API response exceeds limit')
        return json.loads(data)


def source_file(source: str, sha: str, path: str) -> bytes:
    safe_name(path)
    item = api(f'{source}/contents/{urllib.parse.quote(path, safe="/")}?ref={sha}')
    require(item.get('type') == 'file' and item.get('encoding') == 'base64', 'Source file is not inline content')
    data = base64.b64decode(item['content'])
    require(len(data) <= 1024 * 1024, 'Public notice/config exceeds 1 MiB')
    return data


def compare_source(source: str, before: str, after: str) -> str:
    require(bool(SHA.fullmatch(before)) and bool(SHA.fullmatch(after)), 'Invalid source identity')
    return api(f'{source}/compare/{before}...{after}')['status']


def outputs(**values) -> None:
    dest = os.environ.get('GITHUB_OUTPUT')
    if dest:
        with open(dest, 'a', encoding='utf-8') as stream:
            for key, value in values.items():
                text = str(value)
                require('\n' not in text and '\r' not in text, 'Unsafe workflow output')
                stream.write(f'{key}={text}\n')


def resolve(repo: Path, site_id: str, run_id: str, output: Path) -> dict:
    entry = registry(repo)[site_id]
    source = os.environ.get('GITHUB_REPOSITORY', '')
    require(entry['enabled'], f'{site_id} is not enabled in the public registry')
    require(source == entry['producer'], 'Caller does not own this site')
    require(run_id.isdigit(), 'A numeric successful source workflow run ID is required')
    run = api(f'{source}/actions/runs/{run_id}')
    require(run.get('conclusion') == 'success' and run.get('status') == 'completed', 'Source workflow did not pass')
    require(run.get('event') in ('push', 'workflow_dispatch') and run.get('head_branch') == 'main', 'Only trusted main builds may publish')
    require(run['repository']['full_name'] == source and run['head_repository']['full_name'] == source, 'Foreign/fork build rejected')
    require(run.get('path', '').split('@')[0] == entry['workflow'], 'Unexpected source workflow')
    sha = run['head_sha']
    require(bool(SHA.fullmatch(sha)), 'Invalid tested SHA')
    head = api(f'{source}/git/ref/heads/main')['object']['sha']
    require(compare_source(source, sha, head) in ('ahead', 'identical'), 'Tested source is not on current main history')
    config = json.loads(source_file(source, sha, 'web-publish.json'))
    require(config.get('site') == site_id and config.get('schema') == 1 and config.get('enabled') is True, 'Source has not approved this publication')
    name = entry['artifact'].replace('{sha}', sha)
    matches = []
    for page in range(1, 21):
        items = api(f'{source}/actions/runs/{run_id}/artifacts?per_page=100&page={page}')['artifacts']
        matches.extend(x for x in items if x['name'] == name and not x.get('expired'))
        if len(items) < 100:
            break
    require(len(matches) == 1, f'Expected exactly one unexpired artifact named {name}')
    artifact = matches[0]
    require(artifact.get('workflow_run', {}).get('head_sha', sha) == sha, 'Artifact/source mismatch')
    candidate = dict(schema=1, site=site_id, source=source, source_sha=sha, run_id=int(run_id),
                     artifact_id=artifact['id'], artifact_digest=artifact.get('digest'), config=config)
    write_json(output, candidate)
    outputs(artifact_id=artifact['id'], source_sha=sha, source_run=run_id)
    return candidate


def prepare(candidate_file: Path, artifact: Path, payload: Path) -> dict:
    candidate = read_json(candidate_file)
    config = candidate.pop('config')
    stage(artifact, config, payload)
    for item in config.get('source_files', []):
        src, dst = safe_name(item['from']), safe_name(item['to'])
        target = payload / dst
        require(not target.exists(), 'Notice overlaps runtime output')
        data = source_file(candidate['source'], candidate['source_sha'], src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    candidate['digest'] = digest(rows(payload))
    candidate['retain_hashed_assets'] = config.get('retain_hashed_assets') is True
    candidate['smoke'] = config.get('smoke', {})
    write_json(candidate_file, candidate)
    return candidate


def git(repo: Path, *args: str, env: dict | None = None, check: bool = True):
    return subprocess.run(['git', '-C', str(repo), *args], text=True, capture_output=True,
                          check=check, env=env, timeout=120)


def transaction(remote: str, site_id: str, mutate, *, env: dict | None = None,
                before_push=None, retries: int = 8) -> dict:
    """Refresh and reapply OWNED paths, not merge generated trees. Tests use a local bare remote."""
    require(bool(ID.fullmatch(site_id)), 'Invalid site id')
    with tempfile.TemporaryDirectory(prefix='axioms-publication-') as temp:
        checkout = Path(temp) / 'web'
        result = subprocess.run(['git', 'clone', '--depth', '1', '--branch', 'main', remote, str(checkout)],
                                text=True, capture_output=True, env=env, timeout=120)
        require(result.returncode == 0, 'Cannot clone public destination; check network and repository access')
        for attempt in range(retries):
            if attempt:
                git(checkout, 'fetch', '--no-tags', 'origin', 'main', env=env)
                git(checkout, 'reset', '--hard', 'FETCH_HEAD', env=env)
            old_head = git(checkout, 'rev-parse', 'HEAD', env=env).stdout.strip()
            status = mutate(checkout)
            if status != 'publish':
                return {'status': status, 'commit': old_head}
            owned = (f'site/{site_id}', f'releases/{site_id}.json')
            # git add --all handles both removal and new folders; filter via existing tracked paths.
            for name in owned:
                if (checkout / name).exists() or git(checkout, 'ls-files', '--', name, env=env).stdout:
                    git(checkout, 'add', '--all', '--', name, env=env)
            changed = git(checkout, 'diff', '--cached', '--name-only', '-z', env=env).stdout.split('\0')
            require(all(not x or x == owned[1] or x.startswith(owned[0] + '/') for x in changed), 'Attempt to change another owner or infrastructure')
            if not any(changed):
                return {'status': 'unchanged', 'commit': old_head}
            git(checkout, '-c', 'user.name=github-actions[bot]', '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                'commit', '-m', f'publish({site_id}): update owned web output', env=env)
            if before_push:
                before_push(attempt)
            pushed = git(checkout, 'push', 'origin', 'HEAD:main', env=env, check=False)
            if pushed.returncode == 0:
                return {'status': 'published', 'commit': git(checkout, 'rev-parse', 'HEAD', env=env).stdout.strip(), 'attempts': attempt + 1}
            # Retry only if main actually moved. Authentication/ruleset errors fail immediately.
            git(checkout, 'fetch', '--no-tags', 'origin', 'main', env=env)
            latest = git(checkout, 'rev-parse', 'FETCH_HEAD', env=env).stdout.strip()
            require(latest != old_head, 'Push rejected without a concurrent update; check Contents write and main rulesets')
            time.sleep(min(0.15 * 2 ** attempt, 3) + random.random() * 0.1)
        raise ValueError('Concurrent publication retry budget exhausted; rerun this publication (no force push was attempted)')


def promote_mutation(site_id: str, payload: Path, candidate: dict, compare):
    def mutate(repo: Path) -> str:
        entry = registry(repo)[site_id]
        require(entry['enabled'] and candidate['source'] == entry['producer'] and candidate['site'] == site_id, 'Producer/ownership disabled or changed')
        require(digest(rows(payload)) == candidate['digest'], 'Staged bytes changed')
        record = repo / 'releases' / f'{site_id}.json'
        old = read_json(record) if record.exists() else None
        if old:
            validate_state(repo, site_id, old)
        status = decide(old, candidate, compare)
        if status == 'publish':
            install(repo, site_id, payload, candidate, old)
            total = 0
            for path in (repo / 'releases').glob('*.json'):
                s = read_json(path)
                if s.get('active'):
                    total += sum(x['bytes'] for x in s['files'] + s.get('retained', []))
            require(total <= MAX_TOTAL, 'Combined serving budget exceeded; no files were pushed')
        return status
    return mutate


def admin_mutation(site_id: str, operation: str, revision: str | None):
    def mutate(repo: Path) -> str:
        require(site_id in registry(repo), 'Unknown site')
        record = repo / 'releases' / f'{site_id}.json'
        current = read_json(record)
        validate_state(repo, site_id, current)
        if operation == 'restore':
            require(revision is not None and bool(SHA.fullmatch(revision)), 'Restore needs a full web commit SHA')
            git(repo, 'fetch', '--no-tags', 'origin', revision)
            prior = json.loads(git(repo, 'show', f'{revision}:releases/{site_id}.json').stdout)
            require(prior.get('active'), 'Selected revision has no active payload')
            if (repo / 'site' / site_id).exists():
                shutil.rmtree(repo / 'site' / site_id)
            git(repo, 'restore', '--source', revision, '--worktree', '--', f'site/{site_id}')
            prior.update(watermark=current.get('watermark'), suspended=False, restored_from=revision)
            write_json(record, prior)
            validate_state(repo, site_id, prior)
        elif operation == 'unpublish':
            if (repo / 'site' / site_id).exists():
                shutil.rmtree(repo / 'site' / site_id)
            write_json(record, dict(current, active=False, suspended=True, files=[], retained=[]))
        elif operation == 'resume':
            write_json(record, dict(current, suspended=False))
        else:
            raise ValueError('Unknown operation')
        return 'publish'
    return mutate


def public_json(url: str):
    require(url.startswith('https://'), 'Public checks require HTTPS')
    with urllib.request.urlopen(urllib.request.Request(url, headers={'Cache-Control': 'no-cache'}), timeout=20) as response:
        return json.load(response)


def wait_live(site_id: str, candidate: dict, base: str, seconds: int = 360) -> str:
    deadline = time.monotonic() + seconds
    url = base.rstrip('/') + '/' + site_id + '/__release.json'
    while time.monotonic() < deadline:
        try:
            live = public_json(url + '?check=' + str(time.time_ns()))
            if live.get('source_sha') == candidate['source_sha'] and live.get('digest') == candidate['digest']:
                return 'live'
            watermark = live.get('watermark')
            if watermark == candidate['source_sha'] and live.get('source_sha') != watermark:
                return 'superseded-by-restore'
            if watermark and compare_source(candidate['source'], candidate['source_sha'], watermark) == 'ahead':
                return 'superseded-by-newer-live-release'
        except (urllib.error.URLError, ValueError, KeyError):
            pass
        time.sleep(5)
    raise ValueError('Public commit exists but the expected release is not live; inspect web Pages deployment/configuration and redeploy')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('resolve', 'stage', 'promote', 'assemble', 'wait', 'unpublish', 'restore', 'resume', 'check-live'))
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--site')
    parser.add_argument('--run-id', default='')
    parser.add_argument('--candidate', type=Path, default=Path('candidate.json'))
    parser.add_argument('--artifact', type=Path, default=Path('incoming'))
    parser.add_argument('--payload', type=Path, default=Path('payload'))
    parser.add_argument('--output', type=Path, default=Path('_site'))
    parser.add_argument('--commit', default=os.environ.get('GITHUB_SHA', 'local'))
    parser.add_argument('--base-url', default=os.environ.get('WEB_BASE_URL') or BASE_URL)
    args = parser.parse_args()
    if args.command == 'resolve':
        resolve(args.repo, args.site, args.run_id, args.candidate)
        return
    if args.command == 'stage':
        print(json.dumps(prepare(args.candidate, args.artifact, args.payload)))
        return
    if args.command == 'assemble':
        print(json.dumps(assemble(args.repo, args.output, args.commit)))
        return
    if args.command == 'check-live':
        expected = read_json(args.output / 'deployment.json')
        deadline = time.monotonic() + 180
        while True:
            try:
                actual = public_json(args.base_url.rstrip('/') + '/deployment.json?check=' + str(time.time_ns()))
                require(actual == expected, 'Live deployment identity differs')
                for site_id, identity in expected['sites'].items():
                    observed = public_json(args.base_url.rstrip('/') + '/' + site_id + '/__release.json?check=' + str(time.time_ns()))
                    require(observed == identity, 'Live sub-site identity differs')
                print('Verified live deployment', expected['commit'])
                return
            except (urllib.error.URLError, ValueError):
                if time.monotonic() >= deadline:
                    raise ValueError('Pages live identity verification failed')
                time.sleep(5)
    if args.command == 'wait':
        status = wait_live(args.site, read_json(args.candidate), args.base_url)
        print(status)
        outputs(live_status=status)
        return
    token = os.environ.get('PUBLIC_RELEASE_TOKEN', '')
    require(bool(token), 'Set WEB_PUBLISH_APP_ID + WEB_PUBLISH_APP_PRIVATE_KEY, or PUBLIC_RELEASE_TOKEN with Contents write on AxiomsAwake/web')
    with tempfile.TemporaryDirectory(prefix='axioms-auth-') as temp:
        askpass = Path(temp) / 'askpass.sh'
        askpass.write_text('#!/bin/sh\ncase "$1" in *Username*) echo x-access-token;; *) printf "%s\\n" "$PUBLIC_RELEASE_TOKEN";; esac\n')
        askpass.chmod(0o700)
        env = dict(os.environ, GIT_ASKPASS=str(askpass), GIT_TERMINAL_PROMPT='0', GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1')
        if args.command == 'promote':
            candidate = read_json(args.candidate)
            mutate = promote_mutation(args.site, args.payload, candidate, lambda a, b: compare_source(candidate['source'], a, b))
        else:
            mutate = admin_mutation(args.site, args.command, args.commit if args.command == 'restore' else None)
        result = transaction('https://github.com/' + TARGET + '.git', args.site, mutate, env=env)
        print(json.dumps(result))
        outputs(status=result['status'], web_commit=result['commit'], url=args.base_url.rstrip('/') + '/' + args.site + '/')
        summary = os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary, 'a') as stream:
                stream.write(f"## Web publication: {args.site}\n\nRepository state: **{result['status']}**. Web commit: `{result['commit']}`.\n\nSite: {args.base_url.rstrip('/')}/{args.site}/\n\nA repository commit is not yet live acceptance; see the following serving check.\n")


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        # Commands and URLs never contain tokens; do not dump process environments/API bodies.
        raise SystemExit(f'Publication failed: {error}') from None
