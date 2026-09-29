import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('review_transfer', Path(__file__).resolve().parents[1] / '.github/actions/review-upload/review_transfer.py')
transfer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transfer)


class ReviewTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'reports'
        self.root.mkdir()
        self.data = b'original capture bytes'
        (self.root / 'shot.png').write_bytes(self.data)

    def tearDown(self):
        self.temp.cleanup()

    def stage(self, pattern='*.png', **kwargs):
        return transfer.stage(self.root, pattern, self.base, [self.base], **kwargs)

    def test_preserves_original_bytes_and_receipt(self):
        result = self.stage()
        dest = Path(result['directory'])
        self.assertEqual((dest / 'shot.png').read_bytes(), self.data)
        manifest = json.loads((dest / 'transfer-manifest.json').read_text())
        self.assertEqual(manifest['files'][0]['sha256'], hashlib.sha256(self.data).hexdigest())
        self.assertEqual(result['bytes'], sum(p.stat().st_size for p in dest.iterdir()))
        transfer.cleanup(str(dest), self.base)
        self.assertFalse(dest.exists())
        self.assertEqual((self.root / 'shot.png').read_bytes(), self.data)

    def test_overlapping_patterns_do_not_duplicate(self):
        self.assertEqual(self.stage('*.png\nshot.png')['files'], 1)

    def test_no_match_has_no_staging_side_effect(self):
        self.assertFalse(self.stage('*.webm')['ready'])
        self.assertEqual(list(self.base.iterdir()), [self.root])

    def test_byte_budget_has_no_staging_side_effect(self):
        self.assertEqual(self.stage(limit=4)['reason'], 'byte_budget')
        self.assertEqual(list(self.base.iterdir()), [self.root])

    def test_budget_includes_the_manifest(self):
        self.assertEqual(self.stage(limit=len(self.data))['reason'], 'byte_budget')
        self.assertEqual(list(self.base.iterdir()), [self.root])

    def test_file_budget_refuses_instead_of_truncating(self):
        (self.root / 'second.png').write_bytes(b'2')
        self.assertEqual(self.stage(file_limit=1)['reason'], 'file_budget')
        self.assertEqual(list(self.base.iterdir()), [self.root])

    def test_rejects_packages_and_hidden_material(self):
        for name in ('game.pck', 'source.zip', '.secret.json'):
            with self.subTest(name=name):
                (self.root / name).write_bytes(b'not diagnostic')
                with self.assertRaises(ValueError): self.stage(name)
                (self.root / name).unlink()

    def test_rejects_parent_and_absolute_patterns(self):
        for pattern in ('../*.png', '/tmp/*.png', 'sub/../*.png', r'..\*.png', ''):
            with self.subTest(pattern=pattern), self.assertRaises(ValueError):
                self.stage(pattern)

    def test_rejects_symlinked_files_and_directories(self):
        (self.root / 'link.png').symlink_to(self.root / 'shot.png')
        with self.assertRaises(ValueError): self.stage()
        (self.root / 'link.png').unlink()
        link = self.base / 'linked-reports'
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            transfer.stage(link, '*.png', self.base, [self.base])

    def test_rejects_whole_workspace_and_external_root(self):
        with self.assertRaises(ValueError):
            transfer.stage(self.base, '**/*.png', self.base, [self.base])
        with tempfile.TemporaryDirectory() as outside, self.assertRaises(ValueError):
            transfer.stage(Path(outside), '*.png', self.base, [self.base])

    def test_input_cannot_be_overwritten_by_transfer_metadata(self):
        (self.root / 'transfer-manifest.json').write_text('{}')
        with self.assertRaises(ValueError): self.stage('*.json')
        self.assertEqual((self.root / 'transfer-manifest.json').read_text(), '{}')

    def test_cannot_raise_policy_limits(self):
        for kwargs in ({'limit': transfer.MAX_BYTES + 1}, {'file_limit': transfer.MAX_FILES + 1}, {'limit': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): self.stage(**kwargs)

    def test_cleanup_refuses_originals_and_paths_outside_staging(self):
        for directory in (str(self.root), str(self.base), '/tmp/not-ours'):
            with self.subTest(directory=directory), self.assertRaises(ValueError):
                transfer.cleanup(directory, self.base)
        self.assertTrue((self.root / 'shot.png').exists())

    def test_action_requires_manual_opt_in_and_repository_switch(self):
        path = Path(__file__).resolve().parents[1] / '.github/actions/review-upload/action.yml'
        source = path.read_text()
        for contract in ("github.event_name == 'workflow_dispatch'", "inputs.enabled == 'true'", "vars.CI_REVIEW_UPLOADS_ENABLED == 'true'", 'continue-on-error: true', 'retention-days: 1', "steps.stage.outputs.ready == 'true'"):
            self.assertIn(contract, source)
        self.assertEqual(source.count('uses: actions/upload-artifact@'), 1)


if __name__ == '__main__': unittest.main()
