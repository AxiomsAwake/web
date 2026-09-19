"""Native editor bundles must remain complete without admitting hidden secrets."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from contract import MAX_FILE, MAX_SITE, MAX_TOTAL, rows, safe_name, stage


class NativeEditorPayloadTests(unittest.TestCase):
    def test_native_import_sentinels_are_explicitly_safe(self):
        name = 'editors/terrain3d/project/addons/terrain_3d/brushes/.gdignore'
        self.assertEqual(safe_name(name), name)
        self.assertEqual(safe_name('.nojekyll'), '.nojekyll')

    def test_hidden_secrets_and_directories_remain_forbidden(self):
        for name in ['.env', 'project/.env.production', 'project/.git/config',
                     'project/.github/workflows/build.yml', '.gdignore/secret.txt',
                     'project/.gdignore/.env', 'project/private.key',
                     'project/addons/../.gdignore', 'project/.gdignore.js']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_name(name)

    def test_stage_preserves_native_sentinel_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incoming = root / 'incoming'; incoming.mkdir()
            (incoming / 'index.html').write_text('<!doctype html>')
            sentinel = incoming / 'project/addons/terrain/brushes/.gdignore'
            sentinel.parent.mkdir(parents=True)
            sentinel.write_bytes(b'')
            files = stage(incoming, {'schema': 1, 'enabled': True,
                          'files': [{'from': '.', 'to': '.'}]}, root / 'published')
            self.assertIn(sentinel.relative_to(incoming).as_posix(), [item['path'] for item in files])
            self.assertEqual((root / 'published' / sentinel.relative_to(incoming)).read_bytes(), b'')

    def test_complete_editor_binary_fits_below_github_limit(self):
        self.assertEqual(MAX_FILE, 99 * 1024 * 1024)
        self.assertLess(MAX_FILE, 100 * 1024 * 1024)
        self.assertEqual(MAX_SITE, 250 * 1024 * 1024)
        self.assertEqual(MAX_TOTAL, 900 * 1024 * 1024)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'index.html').write_text('<!doctype html>')
            # Sparse input reproduces the observed full-editor side-module size
            # without retaining a large fixture in Git.
            with (root / 'engine.wasm').open('wb') as stream:
                stream.truncate(100_728_711)
            entry = next(item for item in rows(root) if item['path'] == 'engine.wasm')
            self.assertEqual(entry['bytes'], 100_728_711)

    def test_over_budget_binary_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'index.html').write_text('<!doctype html>')
            with (root / 'engine.wasm').open('wb') as stream:
                stream.truncate(MAX_FILE + 1)
            with self.assertRaisesRegex(ValueError, 'File exceeds'):
                rows(root)


if __name__ == '__main__':
    unittest.main()
