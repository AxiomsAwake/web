#!/usr/bin/env python3
"""One diagnostic probe per public identity; never substitutes for serving acceptance."""
from __future__ import annotations
import argparse
import json
import time
import urllib.error
from pathlib import Path
from urllib.parse import urlsplit


def summary(value):
    if not isinstance(value, dict):
        return {'json_type': type(value).__name__}
    allowed = ('commit', 'deployment_commit', 'site', 'source_sha', 'digest', 'run_id')
    return {key: value[key] for key in allowed
            if key in value and isinstance(value[key], (str, int)) and len(str(value[key])) <= 100}


def diagnose(expected, base_url, fetch_json, emit=print):
    base = urlsplit(base_url)
    if (base.scheme != 'https' or not base.netloc or base.username or base.password
            or base.query or base.fragment):
        raise ValueError('Diagnostics require a public HTTPS base without credentials or query parameters')
    sites = expected.get('sites')
    if not isinstance(sites, dict) or len(sites) > 32:
        raise ValueError('Invalid assembled site inventory')
    probes = [('deployment.json', expected)]
    for site, identity in sites.items():
        if not isinstance(site, str) or not site or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in site):
            raise ValueError('Invalid assembled site identifier')
        probes.append((site + '/__release.json', identity))
    records = []
    for path, wanted in probes:
        emit('LIVE_DIAGNOSTIC_REQUEST ' + path)
        started = time.monotonic()
        record = {'path': path, 'expected': summary(wanted)}
        try:
            actual = fetch_json(base_url.rstrip('/') + '/' + path + '?diagnostic=' + str(time.time_ns()))
            record.update(match=actual == wanted, observed=summary(actual))
        except urllib.error.HTTPError as error:
            record.update(match=False, error='HTTPError', status=error.code)
        except urllib.error.URLError as error:
            record.update(match=False, error='URLError', cause=type(error.reason).__name__)
        except Exception as error:
            # Do not echo arbitrary response bodies, headers or configured URLs.
            record.update(match=False, error=type(error).__name__)
        record['seconds'] = round(time.monotonic() - started, 3)
        records.append(record)
        emit('LIVE_DIAGNOSTIC_RESULT ' + json.dumps(record, sort_keys=True))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-url', required=True)
    args = parser.parse_args()
    from live_check import public_json
    from contract import read_json
    expected = read_json(args.output / 'deployment.json')
    diagnose(expected, args.base_url, lambda url: public_json(url, timeout=8),
             lambda line: print(line, flush=True))


if __name__ == '__main__':
    main()
