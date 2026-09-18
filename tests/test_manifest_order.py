import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from contract import digest, install, rows, validate_state


class ManifestOrderTests(unittest.TestCase):
    def test_nested_prefix_names_use_the_same_order_as_release_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = root / 'payload'
            for name in ['index.html', 'lib.png', 'lib/a.js', 'lib/a.png', 'lib/a/b.js']:
                target = payload / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(name)
            manifest = rows(payload)
            self.assertEqual([r['path'] for r in manifest], sorted(r['path'] for r in manifest))
            candidate = {'source_sha': 'a' * 40, 'digest': digest(manifest)}
            state = install(root / 'repo', 'example', payload, candidate, None)
            validate_state(root / 'repo', 'example', state)
            (root / 'repo/site/example/lib/a.js').write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'Release bytes differ'):
                validate_state(root / 'repo', 'example', state)
