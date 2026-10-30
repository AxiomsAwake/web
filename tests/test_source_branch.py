"""Exact registry branch selection preserves the producer trust boundary."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_publishing import A, B, config, init_tree
from contract import read_json, registry, source_branch, write_json
from publish import resolve

BRANCH = 'work/cross-engine-suite-20261025'
ROOT = Path(__file__).resolve().parents[1]


class SourceBranchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_tree(self.root)
        self.run = {
            'conclusion': 'success', 'status': 'completed', 'event': 'workflow_dispatch',
            'head_branch': BRANCH, 'head_sha': A,
            'path': '.github/workflows/verify.yml@refs/heads/' + BRANCH,
            'repository': {'full_name': 'OtherOrg/alpha'},
            'head_repository': {'full_name': 'OtherOrg/alpha'},
        }
        self.comparison = 'ahead'

    def select_branch(self):
        catalog = read_json(self.root / 'catalog/sites.json')
        catalog['sites']['alpha']['source_branch'] = BRANCH
        write_json(self.root / 'catalog/sites.json', catalog)

    def api(self, path):
        if path.endswith('/actions/runs/17'):
            return self.run
        if path.endswith('/git/ref/heads/' + self.run['head_branch']):
            return {'object': {'sha': B}}
        if path.endswith('/compare/' + A + '...' + B):
            return {'status': self.comparison}
        if '/artifacts?' in path:
            return {'artifacts': [{'id': 19, 'name': 'public-site',
                                   'workflow_run': {'head_sha': A}}]}
        raise AssertionError(path)

    def resolve(self, manifest=None):
        with patch.dict('os.environ', {'GITHUB_REPOSITORY': 'OtherOrg/alpha'}), \
             patch('publish.api', side_effect=self.api), \
             patch('publish.source_file', return_value=json.dumps(manifest or config()).encode()):
            return resolve(self.root, 'alpha', '17', self.root / 'candidate.json')

    def test_default_main_remains_compatible_and_rejects_other_branch(self):
        with self.assertRaisesRegex(ValueError, 'registered-branch'):
            self.resolve()
        self.run['head_branch'] = 'main'
        self.assertEqual(self.resolve()['source_sha'], A)

    def test_literal_branch_validation(self):
        self.assertEqual(source_branch({}), 'main')
        for branch in ('main', BRANCH, 'release/v1.2.3'):
            self.assertEqual(source_branch({'source_branch': branch}), branch)
        for branch in ('', None, 1, '*', 'work/*', '../main', 'work/../main',
                       'work//main', '/main', 'main/', 'refs/heads/main', 'HEAD',
                       '-main', 'main.lock', 'work/.hidden', 'main.', 'main?x', 'main#x',
                       'main%2fx', 'main\n', 'main\x00', 'main\t', 'main\\x',
                       'main@{1}', 'main:other', 'main x'):
            with self.subTest(branch=branch):
                catalog = read_json(self.root / 'catalog/sites.json')
                catalog['sites']['alpha']['source_branch'] = branch
                write_json(self.root / 'catalog/sites.json', catalog)
                with self.assertRaisesRegex(ValueError, 'literal source branch'):
                    registry(self.root)

    def test_explicit_branch_accepts_ancestor_and_identical_sha(self):
        self.select_branch()
        for comparison in ('ahead', 'identical'):
            self.comparison = comparison
            self.assertEqual(self.resolve()['artifact_id'], 19)

    def test_explicit_branch_rejects_wrong_branch_and_untrusted_runs(self):
        self.select_branch()
        original = copy.deepcopy(self.run)
        for change in ({'head_branch': 'main'}, {'head_branch': 'work/other'},
                       {'conclusion': 'failure'}, {'status': 'in_progress'},
                       {'event': 'pull_request'}, {'event': 'schedule'},
                       {'repository': {'full_name': 'Foreign/repo'}},
                       {'head_repository': {'full_name': 'Foreign/fork'}},
                       {'path': '.github/workflows/other.yml'}, {'head_sha': 'bad'}):
            with self.subTest(change=change):
                self.run = dict(original, **change)
                with self.assertRaises(ValueError):
                    self.resolve()

    def test_explicit_branch_rejects_non_ancestor_and_wrong_site_manifest(self):
        self.select_branch()
        for comparison in ('behind', 'diverged'):
            self.comparison = comparison
            with self.assertRaisesRegex(ValueError, 'registered branch history'):
                self.resolve()
        self.comparison = 'ahead'
        with self.assertRaisesRegex(ValueError, 'has not approved'):
            self.resolve(dict(config(), site='beta'))

    def test_two_showcase_registrations_use_separate_source_bound_manifests(self):
        sites = registry(ROOT)
        self.assertEqual(source_branch(sites['gamedev']), 'main')
        for site in ('cross-engine-comparison', 'engine-inspiration'):
            entry = sites[site]
            self.assertEqual(source_branch(entry), 'main')
            self.assertNotIn('source_branch', entry)
            self.assertEqual(entry['producer'], 'AxiomsAwake/GameDev')
            self.assertEqual(entry['workflow'], '.github/workflows/cross-engine-web.yml')
            self.assertEqual(entry['release_asset'], site + '-{sha}.zip')
            self.assertEqual(entry['manifest_path'], 'web-publish-' + site + '.json')
            write_json(self.root / 'catalog/sites.json', {'schema': 1, 'sites': {site: entry}})
            self.run.update(repository={'full_name': 'AxiomsAwake/GameDev'},
                            head_repository={'full_name': 'AxiomsAwake/GameDev'},
                            path=entry['workflow'])
            with patch.dict('os.environ', {'GITHUB_REPOSITORY': 'AxiomsAwake/GameDev'}), \
                 patch('publish.api', side_effect=self.api), \
                 patch('publish.source_file', return_value=json.dumps(dict(config(), site='wrong-site')).encode()) as source:
                self.run['head_branch'] = BRANCH
                with self.assertRaisesRegex(ValueError, 'registered-branch'):
                    resolve(self.root, site, '17', self.root / 'candidate.json')
                source.assert_not_called()
                self.run['head_branch'] = 'main'
                with self.assertRaisesRegex(ValueError, 'has not approved'):
                    resolve(self.root, site, '17', self.root / 'candidate.json')
            source.assert_called_once_with('AxiomsAwake/GameDev', A, entry['manifest_path'])
