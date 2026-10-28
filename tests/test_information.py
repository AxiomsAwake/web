"""Maintainer information remains separate from producer-owned releases."""
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from test_publishing import A, candidate, init_tree, payload
from contract import INFORMATION, assemble, install, read_json, registry, write_json
from pages_plan import fingerprint


class InformationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / 'repo'
        init_tree(self.repo)
        self.info = self.repo / 'information/media-publisher'
        original = Path(__file__).resolve().parents[1] / 'information/media-publisher'
        shutil.copytree(original, self.info)
        self.out = self.root / 'output'

    def test_exact_selected_files_without_game_card_or_identity(self):
        game = payload(self.root / 'payload')
        install(self.repo, 'alpha', game, candidate(game), None)
        result = assemble(self.repo, self.out, A)
        self.assertEqual(set(result['sites']), {'alpha'})
        self.assertEqual({p.name for p in (self.out / 'media-publisher').iterdir()}, INFORMATION['media-publisher'])
        for name in INFORMATION['media-publisher']:
            self.assertEqual((self.out / 'media-publisher' / name).read_bytes(), (self.info / name).read_bytes())
        self.assertNotIn('media-publisher', (self.out / 'index.html').read_text())
        self.assertFalse((self.out / 'media-publisher/__release.json').exists())
        self.assertGreaterEqual(result['bytes'], sum(p.stat().st_size for p in self.info.iterdir()))
        before = fingerprint(self.out)[0]
        (self.info / 'privacy.html').write_text('Changed privacy information')
        assemble(self.repo, self.out, A)
        self.assertNotEqual(fingerprint(self.out)[0], before)

    def test_missing_extra_nested_and_secret_files_fail(self):
        for name in ('unexpected.html', 'secret.key', 'nested', '../other.html'):
            with self.subTest(name=name):
                path = self.info / name
                path.mkdir() if name == 'nested' else path.write_text('not selected')
                with self.assertRaises(ValueError):
                    assemble(self.repo, self.out, A)
                path.rmdir() if name == 'nested' else path.unlink()
        (self.info / 'terms.html').unlink()
        with self.assertRaises(ValueError):
            assemble(self.repo, self.out, A)

    def test_symlink_and_input_output_overlap_fail(self):
        (self.info / 'terms.html').unlink()
        (self.info / 'terms.html').symlink_to(self.repo / 'README.md')
        with self.assertRaises(ValueError):
            assemble(self.repo, self.out, A)
        with self.assertRaisesRegex(ValueError, 'inside information'):
            assemble(self.repo, self.info / 'output', A)

    def test_reserved_prefix_cannot_be_registered(self):
        value = read_json(self.repo / 'catalog/sites.json')
        value['sites']['media-publisher'] = value['sites']['alpha']
        write_json(self.repo / 'catalog/sites.json', value)
        with self.assertRaisesRegex(ValueError, 'collides'):
            registry(self.repo)

    def test_information_uses_existing_file_and_combined_budgets(self):
        with patch('contract.MAX_FILE', 1), self.assertRaisesRegex(ValueError, 'File exceeds'):
            assemble(self.repo, self.out, A)
        info_bytes = sum(p.stat().st_size for p in self.info.iterdir())
        game = payload(self.root / 'payload')
        install(self.repo, 'alpha', game, candidate(game), None)
        with patch('contract.MAX_TOTAL', info_bytes), self.assertRaisesRegex(ValueError, '900 MiB'):
            assemble(self.repo, self.out, A)
