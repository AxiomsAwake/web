import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import live_check

BASE = 'https://example.invalid/web/'
EXPECTED = {'schema': 1, 'commit': 'a' * 40, 'sites': {
    'terrain': {'source_sha': 'b' * 40, 'digest': 'c' * 64},
    'unit': {'source_sha': 'd' * 40, 'digest': 'e' * 64}}}


def identities():
    return dict(live_check.inventory(EXPECTED, BASE))


def answer(url, *, timeout):
    return identities()[url.removeprefix(BASE).split('?')[0]]


class ServingTests(unittest.TestCase):
    def test_checks_every_exact_identity(self):
        seen = []
        def fetch(url, *, timeout):
            seen.append(url)
            self.assertLessEqual(timeout, 15)
            return answer(url, timeout=timeout)
        result = live_check.verify(EXPECTED, BASE, fetch=fetch, emit=lambda _: None)
        self.assertEqual(result['identities'], 3)
        self.assertEqual(result['commit'], EXPECTED['commit'])
        self.assertEqual(len(seen), 3)

    def test_subsite_or_root_mismatch_remains_fatal(self):
        for selected in ['deployment.json', 'terrain/__release.json']:
            with self.subTest(path=selected):
                def fetch(url, *, timeout):
                    original = answer(url, timeout=timeout)
                    return dict(original, extra='unexpected') if selected in url else original
                with self.assertRaisesRegex(ValueError, 'IdentityMismatch'):
                    live_check.verify(EXPECTED, BASE, seconds=0.03, fetch=fetch, emit=lambda _: None)

    def test_network_failure_does_not_pass_or_hide_the_path(self):
        def fetch(url, *, timeout):
            raise urllib.error.URLError('secret response body')
        with self.assertRaises(ValueError) as caught:
            live_check.verify(EXPECTED, BASE, seconds=0.03, fetch=fetch, emit=lambda _: None)
        self.assertIn('terrain/__release.json:URLError', str(caught.exception))
        self.assertNotIn('secret response', str(caught.exception))

    def test_eventual_propagation_rechecks_all_identities(self):
        counts = {}
        lock = threading.Lock()
        def fetch(url, *, timeout):
            key = url.split('?')[0]
            with lock:
                counts[key] = counts.get(key, 0) + 1
                count = counts[key]
            return {} if count == 1 else answer(url, timeout=timeout)
        result = live_check.verify(EXPECTED, BASE, seconds=2, fetch=fetch,
                                   sleep=lambda _: None, emit=lambda _: None)
        self.assertEqual(result['attempts'], 2)
        self.assertEqual(list(counts.values()), [2, 2, 2])

    def test_matching_responses_after_deadline_do_not_pass(self):
        now = [0.0]
        def fetch(url, *, timeout):
            now[0] = 2.0
            return answer(url, timeout=timeout)
        with self.assertRaisesRegex(ValueError, 'DeadlineExceeded'):
            live_check.verify(EXPECTED, BASE, seconds=1, fetch=fetch,
                              clock=lambda: now[0], emit=lambda _: None)

    def test_probes_are_actually_concurrent(self):
        barrier = threading.Barrier(3)
        def fetch(url, *, timeout):
            barrier.wait(timeout=1)
            return answer(url, timeout=timeout)
        self.assertEqual(live_check.verify(EXPECTED, BASE, fetch=fetch, emit=lambda _: None)['identities'], 3)

    def test_unsafe_base_and_inventory_never_fetch(self):
        for url in ['http://example.invalid/', 'https://user:password@example.invalid/',
                    BASE + '?token=private', BASE + '#fragment']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                live_check.verify(EXPECTED, url, fetch=lambda *_: self.fail('network'))
        for expected in [{'commit': 'main', 'sites': {}},
                         {**EXPECTED, 'sites': {'../private': {}}},
                         {**EXPECTED, 'sites': {'valid': {}, 7: {}}},
                         {**EXPECTED, 'sites': {str(i): {} for i in range(33)}}]:
            with self.assertRaises(ValueError):
                live_check.verify(expected, BASE, fetch=lambda *_: self.fail('network'))


class TransportTests(unittest.TestCase):
    def test_https_bounds_and_curlrc_is_disabled(self):
        def run(args, **options):
            self.assertEqual(args[:2], ['curl', '--disable'])
            self.assertNotIn('--insecure', args)
            self.assertIn('--max-time', args)
            self.assertIn('--max-filesize', args)
            self.assertEqual(options['timeout'], 0.25)
            Path(args[args.index('--output') + 1]).write_text('{"ok":true}')
            return subprocess.CompletedProcess(args, 0)
        with patch.object(live_check.subprocess, 'run', run):
            self.assertEqual(live_check.public_json(BASE, timeout=0.25), {'ok': True})

    def test_dns_or_process_stall_is_a_bounded_failure(self):
        with patch.object(live_check.subprocess, 'run', side_effect=subprocess.TimeoutExpired('curl', 0.02)):
            with self.assertRaisesRegex(urllib.error.URLError, 'TimeoutExpired'):
                live_check.public_json(BASE, timeout=0.02)

    def test_real_child_process_is_terminated_at_deadline(self):
        original = subprocess.run
        def run(args, **options):
            return original([sys.executable, '-c', 'import time; time.sleep(5)'], **options)
        started = time.monotonic()
        with patch.object(live_check.subprocess, 'run', run), self.assertRaises(urllib.error.URLError):
            live_check.public_json(BASE, timeout=0.04)
        self.assertLess(time.monotonic() - started, 1)

    def test_http_failure_never_returns_a_matching_body(self):
        with patch.object(live_check.subprocess, 'run', return_value=subprocess.CompletedProcess([], 22)):
            with self.assertRaises(urllib.error.URLError):
                live_check.public_json(BASE)

    def test_invalid_or_oversize_responses_are_rejected(self):
        for content in [b'not json', b'x' * (live_check.MAX_JSON + 1), b'\xff']:
            def run(args, **options):
                Path(args[args.index('--output') + 1]).write_bytes(content)
                return subprocess.CompletedProcess(args, 0)
            with patch.object(live_check.subprocess, 'run', run), self.assertRaises(ValueError):
                live_check.public_json(BASE)

    def test_invalid_request_options_never_launch_a_process(self):
        with patch.object(live_check.subprocess, 'run') as run:
            for timeout in [0, -1, float('inf'), 31]:
                with self.assertRaises(ValueError):
                    live_check.public_json(BASE, timeout=timeout)
            with self.assertRaises(ValueError):
                live_check.public_json('http://example.invalid')
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
