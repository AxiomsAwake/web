#!/usr/bin/env python3
"""Delete only this verified deployment's exact temporary Pages artifact."""
import json
import os
import re
import urllib.error
import urllib.request

REPO = 'AxiomsAwake/web'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api(method, path):
    if method not in ('GET', 'DELETE') or not re.fullmatch(r'/actions/artifacts/[1-9][0-9]*', path):
        raise ValueError('Only exact artifact metadata/deletion is allowed')
    request = urllib.request.Request('https://api.github.com/repos/' + REPO + path, method=method,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
            if method == 'DELETE':
                if response.status != 204:
                    raise ValueError('Artifact deletion was not confirmed')
                return None
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError('Oversized artifact metadata')
            return json.loads(raw)
    except urllib.error.HTTPError as error:
        if method == 'GET' and error.code == 404:
            return None
        raise RuntimeError('Artifact operation failed: HTTP ' + str(error.code)) from None


def cleanup(repo, run, attempt, artifact, verified, call=api):
    if repo != REPO or verified is not True:
        raise ValueError('Verified Pages deployment in the owning repository required')
    if not all(re.fullmatch(r'[1-9][0-9]*', str(n)) for n in (run, attempt, artifact)):
        raise ValueError('Exact numeric run, attempt and artifact IDs required')
    path = '/actions/artifacts/' + str(artifact)
    item = call('GET', path)
    if item is None:
        return {'artifact_id': int(artifact), 'status': 'already-absent', 'deleted_bytes': 0}
    if (item.get('id') != int(artifact) or item.get('name') != 'github-pages-' + str(attempt)
            or item.get('workflow_run', {}).get('id') != int(run)):
        raise ValueError('Refusing to delete another run or a non-Pages artifact')
    call('DELETE', path)
    if call('GET', path) is not None:
        raise ValueError('Artifact remains visible after deletion')
    return {'artifact_id': int(artifact), 'status': 'deleted', 'deleted_bytes': item['size_in_bytes']}


if __name__ == '__main__':
    if os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise SystemExit('Only trusted main may clean Pages transport')
    result = cleanup(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_RUN_ID'],
                     os.environ['GITHUB_RUN_ATTEMPT'], os.environ['PAGES_ARTIFACT_ID'],
                     os.environ.get('PAGES_LIVE_VERIFIED') == 'true')
    print('PAGES_CLEANUP ' + json.dumps(result), flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write('\nPages transport cleanup: `' + json.dumps(result) + '`.\n')
