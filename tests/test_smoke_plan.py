import sys
import json
import tempfile
from pathlib import Path
import unittest
from urllib.parse import urlsplit, parse_qs
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from smoke_plan import plan, console_is_error, staged_smoke_config, PLAYER_ENGINE_READY


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


class PlayerStartupTests(unittest.TestCase):
    def test_admitted_threaded_player_requires_positive_engine_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            payload = Path(temp)
            source = 'a' * 40
            build = dict(schema='keepers-player-release-build/v1', target='web', mode='player-demo',
                         selected={'id':'player'}, releaseSource=source, source_revision=source,
                         webStartup='thread-capable')
            (payload / 'build.json').write_text(json.dumps(build))
            config = dict(ready_selector='#canvas', wait_hidden='#status', steps=[{'click':'#canvas'}], touch=True)
            candidate = dict(site='the-keepers', source='AxiomsAwake/TheKeepers', source_sha=source,
                             package_kind='release-asset')
            result = staged_smoke_config('the-keepers', candidate, payload, config)
            self.assertEqual(result, dict(config, ready_selector=PLAYER_ENGINE_READY))
            self.assertEqual(config['ready_selector'], '#canvas')
            # Legacy and other producers retain their existing readiness contract.
            self.assertEqual(staged_smoke_config('the-keepers', candidate, None, config), config)
            self.assertEqual(staged_smoke_config('another-site', candidate, payload, config), config)
            del build['webStartup']; (payload / 'build.json').write_text(json.dumps(build))
            self.assertEqual(staged_smoke_config('the-keepers', candidate, payload, config), config)
            (payload / 'build.json').unlink()
            self.assertEqual(staged_smoke_config('the-keepers', candidate, payload, config), config)

    def test_unknown_or_unbound_threaded_startup_never_uses_premature_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            payload = Path(temp); source = 'a' * 40
            build = dict(schema='keepers-player-release-build/v1', target='web', mode='player-demo',
                         selected={'id':'player'}, releaseSource=source, source_revision=source,
                         webStartup='thread-capable')
            candidate = dict(site='the-keepers', source='AxiomsAwake/TheKeepers', source_sha=source,
                             package_kind='release-asset')
            config = dict(ready_selector='#canvas', wait_hidden='#status')
            for patch in [dict(webStartup='unknown'), dict(releaseSource='b'*40), dict(source_revision='b'*40),
                          dict(target='linux'), dict(schema='unknown')]:
                with self.subTest(patch=patch), self.assertRaises(ValueError):
                    (payload / 'build.json').write_text(json.dumps(dict(build, **patch)))
                    staged_smoke_config('the-keepers', candidate, payload, config)
            (payload / 'build.json').write_text(json.dumps(build))
            with self.assertRaises(ValueError):
                staged_smoke_config('the-keepers', dict(candidate, source='other/repo'), payload, config)
