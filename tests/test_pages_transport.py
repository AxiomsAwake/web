"""Real filesystem fingerprints and fake HTTP controls; no artistic/browser claims."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pages_plan import FIELD, decide, fingerprint, plan, size_report
from pages_cleanup import cleanup, REPO


def fixture(root, commit='a' * 40):
    root.mkdir()
    sites = {}
    for name in ('alpha', 'beta'):
        folder = root / name
        folder.mkdir()
        (folder / 'index.html').write_text('original-' + name)
        sites[name] = {'site': name, 'source_sha': 'b'*40, 'digest': 'c'*64,
                       'watermark': 'b'*40, 'run_id': 100, 'deployment_commit': commit}
        (folder / '__release.json').write_text(json.dumps(sites[name]))
    (root / 'index.html').write_text('catalogue')
    (root / '404.html').write_text('not found')
    (root / '.nojekyll').write_text('')
    (root / 'deployment.json').write_text(json.dumps({'schema': 1, 'commit': commit, 'sites': sites}))
    return root


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = fixture(self.base / 'site')
        self.release = self.base / 'releases'
        self.release.mkdir()

    def run_plan(self, actual=None, verify=None, force=False):
        return plan(self.root, 'https://example.invalid/web/', Mock(return_value=actual),
                    verify or Mock(), releases=self.release, force=force)

    def test_host_commit_does_not_change_fingerprint(self):
        other = fixture(self.base / 'other', 'd'*40)
        self.assertEqual(fingerprint(self.root)[0], fingerprint(other)[0])

    def test_all_real_files_participate(self):
        before = fingerprint(self.root)[0]
        for name in ['alpha/index.html', 'beta/index.html', 'index.html', '404.html', '.nojekyll']:
            with self.subTest(name=name):
                file = self.root / name
                original = file.read_bytes()
                file.write_bytes(original + b'changed')
                self.assertNotEqual(before, fingerprint(self.root)[0])
                file.write_bytes(original)
        (self.root / 'beta' / 'old.12345678.js').write_text('retained compatibility asset')
        self.assertNotEqual(before, fingerprint(self.root)[0])

    def test_rename_and_removal_change_fingerprint(self):
        before = fingerprint(self.root)[0]
        file = self.root / 'alpha/index.html'
        file.rename(self.root / 'alpha/old.html')
        self.assertNotEqual(before, fingerprint(self.root)[0])
        (self.root / 'alpha/old.html').unlink()
        self.assertNotEqual(before, fingerprint(self.root)[0])

    def test_game_identity_is_not_ignored(self):
        before = fingerprint(self.root)[0]
        for key in ('source_sha', 'digest', 'watermark', 'run_id'):
            with self.subTest(key=key):
                identity = json.loads((self.root / 'deployment.json').read_text())
                original = copy.deepcopy(identity)
                identity['sites']['alpha'][key] = 200 if key == 'run_id' else 'e'*64
                (self.root / 'deployment.json').write_text(json.dumps(identity))
                (self.root / 'alpha/__release.json').write_text(json.dumps(identity['sites']['alpha']))
                self.assertNotEqual(before, fingerprint(self.root)[0])
                (self.root / 'deployment.json').write_text(json.dumps(original))
                (self.root / 'alpha/__release.json').write_text(json.dumps(original['sites']['alpha']))

    def test_sidecar_mismatch_and_missing_sidecar_fail(self):
        (self.root / 'alpha/__release.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'sidecar differs'):
            fingerprint(self.root)
        (self.root / 'alpha/__release.json').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing assembled'):
            fingerprint(self.root)

    def test_symlink_rejected(self):
        (self.root / 'leak').symlink_to(self.base)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            fingerprint(self.root)

    def test_missing_or_old_fingerprint_deploys(self):
        self.assertTrue(self.run_plan()['deploy'])
        self.assertTrue(self.run_plan({'commit': 'a'*40})['deploy'])
        value = json.loads((self.root / 'deployment.json').read_text())
        value[FIELD] = 'f'*64
        self.assertTrue(self.run_plan(value)['deploy'])

    def test_same_bytes_skip_only_after_live_verification(self):
        first = self.run_plan()
        actual = json.loads((self.root / 'deployment.json').read_text())
        other = fixture(self.base / 'new', 'd'*40)
        self.root = other
        verifier = Mock()
        second = self.run_plan(actual, verifier)
        self.assertFalse(second['deploy'])
        self.assertEqual(second['served_commit'], 'a'*40)
        self.assertEqual(second['requested_commit'], 'd'*40)
        self.assertEqual(first['content_sha256'], second['content_sha256'])
        self.assertEqual(second['upload_bytes_avoided'], second['payload']['raw_bytes'])
        verifier.assert_called_once_with(actual, 'https://example.invalid/web/', seconds=60)

    def test_failed_live_identity_is_not_unchanged_success(self):
        self.run_plan()
        actual = json.loads((self.root / 'deployment.json').read_text())
        with self.assertRaisesRegex(ValueError, 'drift'):
            self.run_plan(actual, Mock(side_effect=ValueError('live drift')))

    def test_live_read_failure_is_a_deploy_not_false_cache_hit(self):
        result = plan(self.root, 'https://example.invalid/', Mock(side_effect=OSError('offline')),
                      Mock(), releases=self.release)
        self.assertTrue(result['deploy'])
        self.assertIn('unavailable', result['reason'])

    def test_same_digest_with_different_metadata_is_rejected(self):
        self.run_plan()
        expected = json.loads((self.root / 'deployment.json').read_text())
        actual = copy.deepcopy(expected)
        actual['sites']['alpha']['run_id'] = 101
        with self.assertRaisesRegex(ValueError, 'different source'):
            decide(expected, actual)

    def test_forced_redeploy_and_repeat_stamping(self):
        first = self.run_plan()
        actual = json.loads((self.root / 'deployment.json').read_text())
        second = self.run_plan(actual, force=True)
        self.assertTrue(second['deploy'])
        self.assertEqual(first['content_sha256'], second['content_sha256'])
        self.assertEqual(second['payload']['raw_bytes'], sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file()))

    def test_size_report_duplicate_and_retained_bytes(self):
        (self.root / 'alpha/same.bin').write_bytes(b'same' * 10)
        (self.root / 'beta/same.bin').write_bytes(b'same' * 10)
        (self.release / 'alpha.json').write_text(json.dumps({'active': True, 'retained': [{'bytes': 13}]}))
        report = size_report(fingerprint(self.root)[1], self.release)
        self.assertEqual(report['duplicate_bytes'], 40)
        self.assertEqual(report['retained_generation_bytes'], {'alpha': 13})


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.item = {'id': 42, 'name': 'github-pages-1', 'workflow_run': {'id': 100}, 'size_in_bytes': 150}

    def test_only_exact_verified_artifact_deleted_and_absence_checked(self):
        call = Mock(side_effect=[self.item, None, None])
        self.assertEqual(cleanup(REPO, 100, 1, 42, True, call)['deleted_bytes'], 150)
        self.assertEqual([c.args for c in call.call_args_list],
                         [('GET', '/actions/artifacts/42'), ('DELETE', '/actions/artifacts/42'), ('GET', '/actions/artifacts/42')])

    def test_wrong_repo_unverified_and_bad_ids_never_call_api(self):
        for args in [('other/repo', 100, 1, 42, True), (REPO, 100, 1, 42, False), (REPO, 100, 1, '42/zip', True)]:
            with self.subTest(args=args):
                call = Mock()
                with self.assertRaises(ValueError): cleanup(*args, call)
                call.assert_not_called()

    def test_wrong_artifact_name_id_or_run_never_deleted(self):
        for delta in [{'id': 41}, {'name': 'evidence'}, {'name': 'github-pages-2'}, {'workflow_run': {'id': 101}}]:
            with self.subTest(delta=delta):
                call = Mock(return_value={**self.item, **delta})
                with self.assertRaises(ValueError): cleanup(REPO, 100, 1, 42, True, call)
                self.assertEqual(call.call_count, 1)

    def test_no_false_success_on_deletion_or_postcondition_failure(self):
        for response in [[self.item, RuntimeError('network')], [self.item, None, self.item]]:
            with self.subTest(response=response):
                with self.assertRaises((ValueError, RuntimeError)):
                    cleanup(REPO, 100, 1, 42, True, Mock(side_effect=response))

    def test_missing_artifact_is_idempotent_not_a_new_deletion(self):
        call = Mock(return_value=None)
        result = cleanup(REPO, 100, 1, 42, True, call)
        self.assertEqual(result, {'artifact_id': 42, 'status': 'already-absent', 'deleted_bytes': 0})
        self.assertEqual(call.call_count, 1)


if __name__ == '__main__':
    unittest.main()
