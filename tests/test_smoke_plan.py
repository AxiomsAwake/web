import sys
from pathlib import Path
import unittest
from urllib.parse import urlsplit, parse_qs
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from smoke_plan import plan, console_is_error


class SmokePlanTests(unittest.TestCase):
    def test_existing_default_is_unchanged(self):
        config = {'ready_selector': '#play', 'steps': [{'click': '#play'}], 'touch': True}
        self.assertEqual(plan('http://localhost:123/web/alpha/', config), [('default', 'http://localhost:123/web/alpha/', config)])

    def test_routes_stay_in_the_same_origin_and_owned_folder(self):
        config = {'touch': True, 'steps': [{'press': 'Enter'}], 'routes': [{'name': 'design', 'query': {'workspace': 'design-scale'}}]}
        result = plan('https://example.test/web/alpha/', config)
        self.assertEqual(len(result), 2)
        self.assertEqual(urlsplit(result[1][1]).path, '/web/alpha/')
        self.assertEqual(urlsplit(result[1][1]).netloc, 'example.test')
        self.assertEqual(parse_qs(urlsplit(result[1][1]).query), {'workspace': ['design-scale']})
        self.assertEqual(result[1][2]['steps'], [])
        self.assertTrue(result[1][2]['touch'])

    def test_malformed_routes_reject_before_browser_execution(self):
        for routes in [[{'name': '../x'}], [{'name': 'default'}], [{'name': 'x', 'url': 'https://other/'}],
                       [{'name': 'x', 'query': 'bad'}], [{'name': 'x'}] * 9]:
            with self.subTest(routes=routes), self.assertRaises(ValueError):
                plan('https://example.test/web/alpha/', {'routes': routes})

    def test_engine_stderr_errors_are_not_hidden_by_a_canvas_ready_selector(self):
        self.assertTrue(console_is_error('error', 'SCRIPT ERROR: missing resource'))
        self.assertTrue(console_is_error('error', 'Unhandled application error'))
        self.assertFalse(console_is_error('warning', 'software graphics'))
        self.assertFalse(console_is_error('error', 'WARNING: V-Sync mode is unavailable'))
