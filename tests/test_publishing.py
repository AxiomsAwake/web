import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from contract import assemble, decide, digest, install, read_json, registry, rows, safe_name, stage, validate_state, write_json
from publish import admin_mutation, git, promote_mutation, transaction, resolve

A, B, C = 'a' * 40, 'b' * 40, 'c' * 40


def compare(a, b):
    return 'ahead' if a < b else 'behind' if a > b else 'identical'


def config():
    return {'schema': 1, 'enabled': True, 'site': 'alpha', 'files': [{'from': '.', 'to': '.'}]}


def init_tree(root):
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / 'catalog/sites.json', {'schema': 1, 'sites': {
        name: {'producer': f'OtherOrg/{name}', 'enabled': True, 'workflow': '.github/workflows/verify.yml', 'artifact': 'public-site', 'title': name}
        for name in ('alpha', 'beta')}})
    (root / 'catalog/index.html').write_text('<!doctype html><title>Catalogue</title><!-- CARDS -->')
    (root / 'README.md').write_text('Infrastructure must survive every producer.')


def payload(root, text='first'):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'index.html').write_text('<!doctype html><title>Game</title><button id="play">Play</button><script src="./app.js"></script>')
    (root / 'app.js').write_text('document.querySelector("#play").onclick=()=>document.body.dataset.played="yes";' + f'/* {text} */')
    return root


def candidate(root, site='alpha', sha=A):
    return {'site': site, 'source': f'OtherOrg/{site}', 'source_sha': sha, 'run_id': 1, 'digest': digest(rows(root))}


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        init_tree(self.repo)
        self.payload = payload(self.root / 'payload')

    def test_path_guards(self):
        for name in ('../secret', '/root', 'a/../x', 'a//x', 'a\\x', '.github/workflows/x.yml', '.env', 'x.key', 'x.map', 'node_modules/x', '__release.json', 'x%2fy'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_name(name)
        for name in ('assets/image.png', 'scripts/help.py', 'models/city.glb', 'index.wasm', 'credits.txt', '.nojekyll'):
            self.assertEqual(safe_name(name), name)

    def test_symlink_and_lfs(self):
        (self.payload / 'secret').symlink_to(self.repo / 'README.md')
        with self.assertRaises(ValueError):
            rows(self.payload)
        (self.payload / 'secret').unlink()
        (self.payload / 'model.bin').write_text('version https://git-lfs.github.com/spec/v1\n')
        with self.assertRaises(ValueError):
            rows(self.payload)

    def test_select_from_mixed_archive(self):
        artifact = self.root / 'mixed'
        payload(artifact / 'dist')
        (artifact / 'private.txt').write_text('DO NOT PUBLISH')
        c = dict(config(), files=[{'from': 'dist/index.html', 'to': 'index.html'}, {'from': 'dist/app.js', 'to': 'app.js'}])
        out = self.root / 'staged'
        stage(artifact, c, out)
        self.assertFalse((out / 'private.txt').exists())
        self.assertEqual(rows(out), rows(artifact / 'dist'))

    def test_mapping_overlap_and_symlink_parent(self):
        bad = dict(config(), files=[{'from': 'index.html', 'to': 'index.html'}, {'from': 'app.js', 'to': 'index.html'}])
        with self.assertRaises(ValueError):
            stage(self.payload, bad, self.root / 'out')
        self.assertFalse((self.root / 'out').exists())
        (self.payload / 'linked').symlink_to(self.repo, target_is_directory=True)
        bad['files'] = [{'from': 'linked/README.md', 'to': 'index.html'}]
        with self.assertRaises(ValueError):
            stage(self.payload, bad, self.root / 'out')

    def test_disabled_and_unregistered(self):
        with self.assertRaises(ValueError):
            stage(self.payload, dict(config(), enabled=False), self.root / 'out')
        c = dict(candidate(self.payload), source='WrongOrg/alpha')
        with self.assertRaises(ValueError):
            promote_mutation('alpha', self.payload, c, compare)(self.repo)
        r = read_json(self.repo / 'catalog/sites.json')
        r['sites']['../escape'] = r['sites']['alpha']
        write_json(self.repo / 'catalog/sites.json', r)
        with self.assertRaises(ValueError):
            registry(self.repo)

    def test_ancestry_and_idempotence(self):
        c = candidate(self.payload)
        old = install(self.repo, 'alpha', self.payload, c, None)
        self.assertEqual(decide(old, c, compare), 'unchanged')
        self.assertEqual(decide(old, dict(c, source_sha=B), compare), 'publish')
        self.assertEqual(decide(dict(old, watermark=B), c, compare), 'superseded')
        with self.assertRaises(ValueError):
            decide(old, dict(c, digest='different'), compare)
        with self.assertRaises(ValueError):
            decide(old, dict(c, source_sha=B), lambda a, b: 'diverged')

    def test_bytes_cannot_change_after_gate(self):
        c = candidate(self.payload)
        (self.payload / 'app.js').write_text('changed')
        with self.assertRaises(ValueError):
            promote_mutation('alpha', self.payload, c, compare)(self.repo)

    def test_tampered_release_rejected(self):
        s = install(self.repo, 'alpha', self.payload, candidate(self.payload), None)
        (self.repo / 'site/alpha/app.js').write_text('tampered')
        with self.assertRaises(ValueError):
            validate_state(self.repo, 'alpha', s)

    def test_retention_is_bounded(self):
        assets = self.payload / 'assets'
        assets.mkdir()
        one, two, three = ('world.' + x * 20 + '.js' for x in ('a', 'b', 'c'))
        (assets / one).write_text('first asset')
        c = dict(candidate(self.payload), retain_hashed_assets=True)
        s = install(self.repo, 'alpha', self.payload, c, None)
        (assets / one).unlink()
        (assets / two).write_text('second asset')
        s = install(self.repo, 'alpha', self.payload, dict(candidate(self.payload, sha=B), retain_hashed_assets=True), s)
        self.assertTrue((self.repo / 'site/alpha/assets' / one).exists())
        (assets / two).unlink()
        (assets / three).write_text('third asset')
        s = install(self.repo, 'alpha', self.payload, dict(candidate(self.payload, sha=C), retain_hashed_assets=True), s)
        self.assertFalse((self.repo / 'site/alpha/assets' / one).exists())
        self.assertTrue((self.repo / 'site/alpha/assets' / two).exists())
        validate_state(self.repo, 'alpha', s)

    def test_complete_catalogue_and_no_private_files(self):
        for name in ('alpha', 'beta'):
            install(self.repo, name, self.payload, candidate(self.payload, name), None)
        out = self.root / 'served/web'
        result = assemble(self.repo, out, B)
        self.assertEqual(set(result['sites']), {'alpha', 'beta'})
        self.assertTrue((out / 'alpha/app.js').exists())
        self.assertIn('./beta/', (out / 'index.html').read_text())
        self.assertFalse((out / 'README.md').exists())
        self.assertEqual(read_json(out / 'alpha/__release.json')['deployment_commit'], B)
        (self.repo / 'site/unregistered').mkdir()
        with self.assertRaises(ValueError):
            assemble(self.repo, out, B)

    def test_safe_assembly_destination(self):
        with self.assertRaises(ValueError):
            assemble(self.repo, self.root, A)
        with self.assertRaises(ValueError):
            assemble(self.repo, self.repo / 'site/output', A)
        self.assertTrue((self.repo / 'README.md').exists())


class GitPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        seed = self.root / 'seed'
        init_tree(seed)
        git(seed, 'init', '-b', 'main')
        git(seed, 'add', '.')
        git(seed, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'seed')
        self.remote = self.root / 'remote.git'
        subprocess.run(['git', 'clone', '--bare', str(seed), str(self.remote)], check=True, capture_output=True)
        self.url = self.remote.as_uri()
        self.a = payload(self.root / 'a')
        self.b = payload(self.root / 'b', 'second')

    def publish(self, site='alpha', sha=A, root=None, before=None):
        root = root or self.a
        return transaction(self.url, site, promote_mutation(site, root, candidate(root, site, sha), compare), before_push=before)

    def read_remote(self, name):
        return git(self.remote, 'show', 'main:' + name).stdout

    def test_simultaneous_different_games_both_survive(self):
        barrier = threading.Barrier(2)
        def rendezvous(attempt):
            if attempt == 0:
                barrier.wait(timeout=10)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(self.publish, site=name, before=rendezvous) for name in ('alpha', 'beta')]
            results = [f.result(timeout=30) for f in futures]
        self.assertTrue(all(x['status'] == 'published' for x in results))
        self.assertTrue(any(x['attempts'] == 2 for x in results))
        self.assertIn('first', self.read_remote('site/alpha/app.js'))
        self.assertIn('first', self.read_remote('site/beta/app.js'))
        self.assertEqual(self.read_remote('README.md'), 'Infrastructure must survive every producer.')

    def test_same_game_race_never_regresses(self):
        self.publish(sha=A)
        self.publish(sha=B, root=self.b)
        stale = self.publish(sha=A)
        self.assertEqual(stale['status'], 'superseded')
        self.assertIn('second', self.read_remote('site/alpha/app.js'))
        duplicate = self.publish(sha=B, root=self.b)
        self.assertEqual(duplicate['status'], 'unchanged')

    def test_restore_preserves_watermark_against_old_queued_build(self):
        first = self.publish(sha=A)
        self.publish(sha=B, root=self.b)
        transaction(self.url, 'alpha', admin_mutation('alpha', 'restore', first['commit']))
        old_job = self.publish(sha=B, root=self.b)
        self.assertEqual(old_job['status'], 'superseded')
        record = json.loads(self.read_remote('releases/alpha.json'))
        self.assertEqual((record['source_sha'], record['watermark']), (A, B))
        self.assertIn('first', self.read_remote('site/alpha/app.js'))
        self.assertEqual(self.publish(sha=C, root=self.b)['status'], 'published')

    def test_unpublish_blocks_recreation_and_resume_allows_new_source(self):
        self.publish()
        transaction(self.url, 'alpha', admin_mutation('alpha', 'unpublish', None))
        self.assertEqual(self.publish(sha=B)['status'], 'suspended')
        self.assertNotEqual(git(self.remote, 'show', 'main:site/alpha/index.html', check=False).returncode, 0)
        transaction(self.url, 'alpha', admin_mutation('alpha', 'resume', None))
        self.assertEqual(self.publish(sha=A)['status'], 'superseded')
        self.assertEqual(self.publish(sha=B)['status'], 'published')

    def test_changed_foreign_folder_cannot_be_staged(self):
        def bad(repo):
            (repo / 'README.md').write_text('unrelated edit')
            git(repo, 'add', 'README.md')
            return 'publish'
        with self.assertRaises(ValueError):
            transaction(self.url, 'alpha', bad)
        self.assertEqual(self.read_remote('README.md'), 'Infrastructure must survive every producer.')


if __name__ == '__main__':
    unittest.main()
