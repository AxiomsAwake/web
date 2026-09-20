import sys
from pathlib import Path
import unittest
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from live_diagnostics import diagnose


class LiveDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.expected = {'schema': 1, 'commit': 'a' * 40,
                         'sites': {'example': {'source_sha': 'b' * 40, 'digest': 'c' * 64}}}
        self.messages = []

    def run_probe(self, fetch, base='https://example.invalid/web/'):
        return diagnose(self.expected, base, fetch, self.messages.append)

    def test_matching_complete_and_subsite_identities(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return self.expected if '/deployment.json?' in url else self.expected['sites']['example']
        records = self.run_probe(fetch)
        self.assertEqual([r['match'] for r in records], [True, True])
        self.assertTrue(all('?diagnostic=' in url for url in calls))
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.messages[0], 'LIVE_DIAGNOSTIC_REQUEST deployment.json')

    def test_stale_deployment_and_foreign_json_are_not_matches(self):
        values = iter([{'schema': 1, 'commit': 'd' * 40, 'sites': {}}, []])
        records = self.run_probe(lambda _: next(values))
        self.assertFalse(any(r['match'] for r in records))
        self.assertEqual(records[0]['observed']['commit'], 'd' * 40)
        self.assertEqual(records[1]['observed'], {'json_type': 'list'})

    def test_network_failure_retains_path_and_continues_without_retry(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if len(calls) == 1:
                raise URLError('potentially private environment message')
            raise HTTPError(url, 404, 'arbitrary response', {}, None)
        records = self.run_probe(fetch)
        self.assertEqual(len(calls), 2)
        self.assertEqual(records[0]['error'], 'URLError')
        self.assertEqual(records[1]['status'], 404)
        self.assertNotIn('private', '\n'.join(self.messages))
        self.assertNotIn('arbitrary', '\n'.join(self.messages))

    def test_unsafe_base_or_site_never_reaches_network(self):
        def fetch(_):
            self.fail('Unsafe diagnostic input reached the network')
        for url in ['http://example.invalid/', 'https://user:secret@example.invalid/',
                    'https://example.invalid/?token=secret', 'https://example.invalid/#secret']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.run_probe(fetch, url)
        self.expected['sites'] = {'../other': {}}
        with self.assertRaises(ValueError):
            self.run_probe(fetch)

    def test_unbounded_inventory_and_response_fields_are_not_echoed(self):
        records = self.run_probe(lambda _: {'source_sha': 'x' * 1000, 'secret': 'do not log'})
        self.assertTrue(all(record['observed'] == {} for record in records))
        self.assertNotIn('do not log', '\n'.join(self.messages))
        self.expected['sites'] = {str(i): {} for i in range(33)}
        with self.assertRaises(ValueError):
            self.run_probe(lambda _: self.fail('Too many diagnostic requests'))


if __name__ == '__main__':
    unittest.main()
