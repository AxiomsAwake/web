#!/usr/bin/env python3
"""Fingerprint the assembled payload; skip transport only after live identity verification."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error

FIELD = 'content_sha256'
SHA = re.compile(r'[a-f0-9]{40}\Z')
SITE = re.compile(r'[a-z][a-z0-9-]{0,47}\Z')


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def normalized(identity):
    """Ignore ONLY host-deployment bookkeeping, never producer or game identities."""
    value = copy.deepcopy(identity)
    if not isinstance(value, dict) or not SHA.fullmatch(str(value.get('commit', ''))):
        raise ValueError('Expected an exact deployment commit')
    commit = value.pop('commit')
    value.pop(FIELD, None)
    sites = value.get('sites')
    if not isinstance(sites, dict) or len(sites) > 32:
        raise ValueError('Invalid deployment sites')
    for site, item in sites.items():
        if not SITE.fullmatch(site) or not isinstance(item, dict) or item.get('deployment_commit') != commit:
            raise ValueError('Inconsistent deployment bookkeeping')
        item.pop('deployment_commit')
    return value


def fingerprint(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Expected an assembled directory')
    identity = json.loads((root / 'deployment.json').read_bytes())
    stable = normalized(identity)
    names = {site + '/__release.json': item for site, item in identity['sites'].items()}
    entries, raw_rows = [], []
    for file in sorted(root.rglob('*')):
        if file.is_symlink():
            raise ValueError('Payload symlinks are forbidden')
        if file.is_dir():
            continue
        if not file.is_file():
            raise ValueError('Special files are forbidden')
        name = file.relative_to(root).as_posix()
        with file.open('rb') as source:
            hasher = hashlib.sha256()
            for block in iter(lambda: source.read(1024 * 1024), b''):
                hasher.update(block)
            sha = hasher.hexdigest()
        raw_rows.append({'path': name, 'bytes': file.stat().st_size, 'sha256': sha})
        if name == 'deployment.json':
            data = encoded(stable)
        elif name in names:
            item = json.loads(file.read_bytes())
            if item != names[name]:
                raise ValueError('Assembled sidecar differs from deployment: ' + name)
            item.pop('deployment_commit')
            data = encoded(item)
        else:
            entries.append({'path': name, 'bytes': file.stat().st_size, 'sha256': sha})
            continue
        entries.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    if not set(names).issubset({r['path'] for r in entries}):
        raise ValueError('Missing assembled release sidecar')
    return hashlib.sha256(encoded(entries)).hexdigest(), raw_rows, identity


def size_report(rows, releases):
    groups, duplicates = {}, {}
    for row in rows:
        site = row['path'].split('/')[0] if '/' in row['path'] else '(catalogue)'
        groups[site] = groups.get(site, 0) + row['bytes']
        duplicates.setdefault((row['sha256'], row['bytes']), []).append(row['path'])
    retained = {}
    for file in sorted(releases.glob('*.json')):
        state = json.loads(file.read_bytes())
        if state.get('active'):
            retained[file.stem] = sum(r['bytes'] for r in state.get('retained', []))
    copies = [{'sha256': sha, 'bytes_each': size, 'paths': paths, 'duplicate_bytes': size * (len(paths)-1)}
              for (sha, size), paths in duplicates.items() if len(paths) > 1 and size > 0]
    return {'raw_bytes': sum(r['bytes'] for r in rows), 'files': len(rows),
            'sites_bytes': groups, 'retained_generation_bytes': retained,
            'largest_files': sorted(rows, key=lambda r: r['bytes'], reverse=True)[:15],
            'duplicate_bytes': sum(r['duplicate_bytes'] for r in copies),
            'largest_duplicate_groups': sorted(copies, key=lambda r: r['duplicate_bytes'], reverse=True)[:10]}


def decide(expected, actual):
    if not isinstance(actual, dict) or actual.get(FIELD) != expected[FIELD]:
        return 'deploy'
    if normalized(actual) != normalized(expected):
        raise ValueError('Matching fingerprint with different source identities; investigate')
    return 'verify-existing'


def plan(root, base_url, fetch, verify, *, releases=Path('releases'), force=False):
    value, rows, expected = fingerprint(root)
    expected[FIELD] = value
    # Only generated host metadata changes. The game folders' source bytes are untouched.
    (root / 'deployment.json').write_text(json.dumps(expected, sort_keys=True, indent=2) + '\n')
    for row in rows:
        if row['path'] == 'deployment.json':
            data = (root / 'deployment.json').read_bytes()
            row.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    report = {'schema': 'axioms-pages-plan/v1', 'requested_commit': expected['commit'],
              'content_sha256': value, 'deploy': True, 'reason': 'content-changed-or-legacy',
              'payload': size_report(rows, releases), 'upload_bytes_avoided': 0}
    if force:
        report['reason'] = 'explicit-redeploy'
        return report
    try:
        actual = fetch(base_url.rstrip('/') + '/deployment.json?plan=' + str(time.time_ns()), timeout=15)
    except (OSError, ValueError, urllib.error.URLError) as error:
        report['reason'] = 'live-state-unavailable-' + type(error).__name__
        return report
    if decide(expected, actual) == 'verify-existing':
        # Verify all existing site sidecars at the actual served host commit, not today's request.
        verify(actual, base_url, seconds=60)
        report.update(deploy=False, reason='identical-verified-live-content',
                      served_commit=actual['commit'], upload_bytes_avoided=report['payload']['raw_bytes'])
    return report


def main():
    from live_check import public_json, verify, validate_url
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    validate_url(args.base_url, base=True)
    if args.report.resolve().is_relative_to(args.output.resolve()):
        parser.error('The diagnostic report must remain outside the public payload')
    report = plan(args.output, args.base_url, public_json, verify, force=args.force)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('deploy=' + str(report['deploy']).lower() + '\n')
    print('PAGES_PLAN ' + json.dumps(report, sort_keys=True), flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write('## Pages transport plan\n\n' + report['reason'] + '\n\n')
            stream.write(f"Fingerprint: `{report['content_sha256']}`\n\n")
            stream.write('| Folder | Raw bytes | Retained-generation bytes |\n| --- | ---: | ---: |\n')
            for site, size in sorted(report['payload']['sites_bytes'].items()):
                stream.write(f"| {site} | {size} | {report['payload']['retained_generation_bytes'].get(site, 0)} |\n")
            stream.write(f"\nRaw payload bytes avoided this run: {report['upload_bytes_avoided']}. "
                         'This is not compressed-byte billing or gameplay acceptance.\n')


if __name__ == '__main__':
    main()
