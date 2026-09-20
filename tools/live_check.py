#!/usr/bin/env python3
"""Bounded public serving verification, including DNS and every accepted sub-site."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
from urllib.parse import urlsplit

MAX_JSON = 256 * 1024
MAX_SITES = 32
WORKERS = 4


def validate_url(url: str, *, base: bool = False) -> None:
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.fragment or (base and parsed.query)
            or any(ord(c) < 33 for c in url)):
        raise ValueError('Public verification requires an HTTPS URL without credentials or fragments')


def public_json(url: str, timeout: float = 15):
    """curl's network deadline plus a process deadline also bound DNS resolution.

    No credentials, response bodies or arbitrary stderr are logged. curlrc is
    disabled; HTTPS certificate verification and HTTPS-only redirects stay on.
    """
    validate_url(url)
    if not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError('Invalid public request deadline')
    with tempfile.TemporaryDirectory(prefix='axioms-live-') as temporary:
        output = Path(temporary) / 'identity.json'
        args = ['curl', '--disable', '--silent', '--show-error', '--fail', '--location',
                '--proto', '=https', '--proto-redir', '=https', '--max-redirs', '3',
                '--connect-timeout', str(min(5, timeout)), '--max-time', str(timeout),
                '--max-filesize', str(MAX_JSON), '--header', 'Cache-Control: no-cache',
                '--output', str(output), '--url', url]
        try:
            result = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=timeout, check=False)
        except (subprocess.TimeoutExpired, OSError) as error:
            raise urllib.error.URLError(type(error).__name__) from None
        if result.returncode:
            raise urllib.error.URLError('Public request failed (curl exit %d)' % result.returncode)
        if not output.is_file() or output.stat().st_size > MAX_JSON:
            raise ValueError('Public identity exceeds the response budget or is absent')
        try:
            return json.loads(output.read_bytes())
        except (ValueError, UnicodeError):
            raise ValueError('Public identity is not valid JSON') from None


def inventory(expected: dict, base_url: str):
    validate_url(base_url, base=True)
    if not isinstance(expected, dict) or not re.fullmatch('[a-f0-9]{40}', str(expected.get('commit', ''))):
        raise ValueError('An exact assembled deployment commit is required')
    sites = expected.get('sites')
    if not isinstance(sites, dict) or len(sites) > MAX_SITES:
        raise ValueError('Invalid assembled site inventory')
    probes = [('deployment.json', expected)]
    for site, identity in sites.items():
        if not isinstance(site, str) or not re.fullmatch('[a-z][a-z0-9-]{0,47}', site) or not isinstance(identity, dict):
            raise ValueError('Invalid assembled sub-site identity')
        probes.append((site + '/__release.json', identity))
    return [probes[0], *sorted(probes[1:])]


def verify(expected: dict, base_url: str, *, seconds: float = 180, fetch=public_json,
           emit=print, clock=time.monotonic, sleep=time.sleep) -> dict:
    probes = inventory(expected, base_url)
    if not math.isfinite(seconds) or not 0 < seconds <= 600:
        raise ValueError('Invalid verification deadline')
    started = clock()
    deadline = started + seconds
    attempt = 0
    failures = []
    while clock() < deadline:
        attempt += 1
        # Each worker's request is hard-bounded. Budget for all waves, so executor
        # shutdown cannot inherit an unbounded DNS or socket operation.
        request_seconds = min(15.0, max(0.001, (deadline - clock()) / math.ceil(len(probes) / WORKERS)))
        nonce = str(time.time_ns())
        failures = []
        def probe(item):
            path, wanted = item
            emit('LIVE_CHECK_REQUEST ' + json.dumps({'path': path, 'attempt': attempt}))
            began = clock()
            try:
                actual = fetch(base_url.rstrip('/') + '/' + path + '?check=' + nonce,
                               timeout=request_seconds)
                result = {'path': path, 'match': actual == wanted}
                if not result['match']:
                    result['error'] = 'IdentityMismatch'
            except (urllib.error.URLError, ValueError, OSError) as error:
                result = {'path': path, 'match': False, 'error': type(error).__name__}
            result['seconds'] = round(clock() - began, 3)
            return result
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for future in as_completed([pool.submit(probe, item) for item in probes]):
                result = future.result()
                emit('LIVE_CHECK_RESULT ' + json.dumps(result, sort_keys=True))
                if not result['match']:
                    failures.append(result['path'] + ':' + result['error'])
        if clock() > deadline:
            failures.append('verification:DeadlineExceeded')
        if not failures:
            result = {'commit': expected['commit'], 'identities': len(probes), 'attempts': attempt,
                      'seconds': round(clock() - started, 3)}
            emit('Verified live deployment ' + expected['commit'])
            return result
        remaining = deadline - clock()
        if remaining > 0:
            sleep(min(5, remaining))
    raise ValueError('Pages live identity verification failed: ' + ', '.join(sorted(failures)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-url', default=os.environ.get('WEB_BASE_URL'))
    args = parser.parse_args()
    if not args.base_url:
        parser.error('An explicit public base URL is required')
    source = args.output / 'deployment.json'
    if not source.is_file() or source.stat().st_size > MAX_JSON:
        raise ValueError('Missing or oversized assembled deployment identity')
    expected = json.loads(source.read_bytes())
    result = verify(expected, args.base_url, emit=lambda line: print(line, flush=True))
    print('LIVE_CHECK_PASSED ' + json.dumps(result), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from None
