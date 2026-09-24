import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from contract import assemble, decide, digest, install, read_json, registry, rows, safe_name, stage, validate_state, write_json
from publish import admin_mutation, git, promote_mutation, transaction, resolve, unpack_release

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

    def test_registry_rejects_unsafe_or_non_json_manifest_paths(self):
        original = read_json(self.repo / 'catalog/sites.json')
        for manifest_path in ('../web-publish.json', '/web-publish.json', '.github/config.json',
                              'nested\\config.json', 'web-publish.yaml', ''):
            with self.subTest(manifest_path=manifest_path):
                value = json.loads(json.dumps(original))
                value['sites']['alpha']['manifest_path'] = manifest_path
                write_json(self.repo / 'catalog/sites.json', value)
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

    def test_release_zip_digest_and_paths_are_enforced(self):
        archive = self.root / 'release.zip'
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('index.html', '<!doctype html>')
            bundle.writestr('app.js', 'ok')
        candidate_file = self.root / 'candidate.json'
        write_json(candidate_file, {
            'package_kind': 'release-asset', 'release_asset_size': archive.stat().st_size,
            'artifact_digest': 'sha256:' + hashlib.sha256(archive.read_bytes()).hexdigest(),
        })
        extracted = self.root / 'incoming'
        unpack_release(candidate_file, archive, extracted)
        self.assertEqual((extracted / 'app.js').read_text(), 'ok')
        archive.write_bytes(archive.read_bytes() + b'tampered')
        with self.assertRaises(ValueError):
            unpack_release(candidate_file, archive, self.root / 'tampered')

    def test_release_zip_cannot_escape_destination(self):
        archive = self.root / 'unsafe.zip'
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('../outside.txt', 'no')
        candidate_file = self.root / 'candidate.json'
        write_json(candidate_file, {
            'package_kind': 'release-asset', 'release_asset_size': archive.stat().st_size,
            'artifact_digest': 'sha256:' + hashlib.sha256(archive.read_bytes()).hexdigest(),
        })
        with self.assertRaises(ValueError):
            unpack_release(candidate_file, archive, self.root / 'unsafe')
        self.assertFalse((self.root / 'outside.txt').exists())


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        init_tree(self.root)

    def manifest_gate_api(self, path):
        if path.endswith('/actions/runs/17'):
            return {
                'conclusion': 'success', 'status': 'completed', 'event': 'push',
                'head_branch': 'main', 'head_sha': A,
                'path': '.github/workflows/verify.yml@refs/heads/main',
                'repository': {'full_name': 'OtherOrg/alpha'},
                'head_repository': {'full_name': 'OtherOrg/alpha'},
            }
        if path.endswith('/git/ref/heads/main'):
            return {'object': {'sha': A}}
        if '/compare/' in path:
            return {'status': 'identical'}
        raise AssertionError(path)

    def test_default_manifest_path_is_backward_compatible(self):
        with patch.dict('os.environ', {'GITHUB_REPOSITORY': 'OtherOrg/alpha'}), \
             patch('publish.api', side_effect=self.manifest_gate_api), \
             patch('publish.source_file', side_effect=ValueError('missing')) as source:
            with self.assertRaisesRegex(ValueError, 'missing'):
                resolve(self.root, 'alpha', '17', self.root / 'candidate.json')
        source.assert_called_once_with('OtherOrg/alpha', A, 'web-publish.json')

    def test_registry_selected_manifest_is_used_without_default_fallback(self):
        catalog = read_json(self.root / 'catalog/sites.json')
        catalog['sites']['alpha']['manifest_path'] = 'manifests/alpha-publication.json'
        write_json(self.root / 'catalog/sites.json', catalog)
        with patch.dict('os.environ', {'GITHUB_REPOSITORY': 'OtherOrg/alpha'}), \
             patch('publish.api', side_effect=self.manifest_gate_api), \
             patch('publish.source_file', side_effect=ValueError('missing selected manifest')) as source:
            with self.assertRaisesRegex(ValueError, 'missing selected manifest'):
                resolve(self.root, 'alpha', '17', self.root / 'candidate.json')
        source.assert_called_once_with('OtherOrg/alpha', A, 'manifests/alpha-publication.json')

    def test_wrong_site_in_registry_selected_manifest_is_rejected(self):
        catalog = read_json(self.root / 'catalog/sites.json')
        catalog['sites']['alpha']['manifest_path'] = 'web-publish-suite.json'
        write_json(self.root / 'catalog/sites.json', catalog)
        wrong = dict(config(), site='beta')
        with patch.dict('os.environ', {'GITHUB_REPOSITORY': 'OtherOrg/alpha'}), \
             patch('publish.api', side_effect=self.manifest_gate_api), \
             patch('publish.source_file', return_value=json.dumps(wrong).encode()) as source:
            with self.assertRaisesRegex(ValueError, 'has not approved'):
                resolve(self.root, 'alpha', '17', self.root / 'candidate.json')
        source.assert_called_once_with('OtherOrg/alpha', A, 'web-publish-suite.json')

    def test_release_asset_is_bound_to_run_sha_tag_and_digest(self):
        catalog = read_json(self.root / 'catalog/sites.json')
        catalog['sites']['alpha'].pop('artifact')
        catalog['sites']['alpha']['release_asset'] = 'Game-{tag}-web.zip'
        write_json(self.root / 'catalog/sites.json', catalog)
        run = {
            'conclusion': 'success', 'status': 'completed', 'event': 'workflow_dispatch',
            'head_branch': 'main', 'head_sha': A, 'path': '.github/workflows/verify.yml@refs/heads/main',
            'repository': {'full_name': 'OtherOrg/alpha'}, 'head_repository': {'full_name': 'OtherOrg/alpha'},
            'run_started_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:10:00Z',
        }
        release = {
            'id': 5, 'target_commitish': A, 'draft': False, 'prerelease': True,
            'tag_name': 'v1', 'published_at': '2026-01-01T00:05:00Z',
            'assets': [{'id': 9, 'name': 'Game-v1-web.zip', 'size': 12,
                        'digest': 'sha256:' + '1' * 64,
                        'created_at': '2026-01-01T00:06:00Z', 'updated_at': '2026-01-01T00:06:01Z'}],
        }
        # The releases listing may omit a freshly uploaded asset even when the
        # dedicated collection already has it. The collection is authoritative.
        assets = release['assets']
        release['assets'] = []
        def fake_api(path):
            if '/actions/runs/17' in path: return run
            if '/git/ref/heads/main' in path: return {'object': {'sha': A}}
            if '/compare/' in path: return {'status': 'identical'}
            if '/releases?' in path: return [release]
            if '/releases/5/assets?' in path: return assets
            if '/git/ref/tags/v1' in path: return {'object': {'type': 'commit', 'sha': A}}
            raise AssertionError(path)
        output = self.root / 'candidate.json'
        with patch.dict('os.environ', {'GITHUB_REPOSITORY': 'OtherOrg/alpha'}), \
             patch('publish.api', side_effect=fake_api), \
             patch('publish.source_file', return_value=json.dumps(config()).encode()):
            resolved = resolve(self.root, 'alpha', '17', output)
        self.assertEqual(resolved['package_kind'], 'release-asset')
        self.assertEqual((resolved['source_sha'], resolved['release_tag'], resolved['release_asset_id']), (A, 'v1', 9))
        assets.append(dict(assets[0], id=10))
        with patch.dict('os.environ', {'GITHUB_REPOSITORY': 'OtherOrg/alpha'}), \
             patch('publish.api', side_effect=fake_api), \
             patch('publish.source_file', return_value=json.dumps(config()).encode()):
            with self.assertRaisesRegex(ValueError, 'Expected exactly one release asset'):
                resolve(self.root, 'alpha', '17', self.root / 'duplicate.json')

    def test_registered_stable_release_is_bound_to_source_manifest(self):
        catalog = read_json(self.root / 'catalog/sites.json')
        catalog['sites']['alpha'].pop('artifact')
        catalog['sites']['alpha'].update(release_asset='Game-{tag}-web.zip', accepted_release_channels=['prerelease', 'stable'],
                                         release_manifest_path='release/manifest.json')
        write_json(self.root / 'catalog/sites.json', catalog)
        run = {
            'conclusion': 'success', 'status': 'completed', 'event': 'workflow_dispatch',
            'head_branch': 'main', 'head_sha': A, 'path': '.github/workflows/verify.yml@refs/heads/main',
            'repository': {'full_name': 'OtherOrg/alpha'}, 'head_repository': {'full_name': 'OtherOrg/alpha'},
            'run_started_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:10:00Z',
        }
        release = {
            'id': 5, 'target_commitish': A, 'draft': False, 'prerelease': False,
            'tag_name': 'v1.2.3', 'published_at': '2026-01-01T00:05:00Z',
            'assets': [{'id': 9, 'name': 'Game-v1.2.3-web.zip', 'size': 12,
                        'digest': 'sha256:' + '1' * 64,
                        'created_at': '2026-01-01T00:06:00Z', 'updated_at': '2026-01-01T00:06:01Z'}],
        }
        def fake_api(path):
            if '/actions/runs/17' in path: return run
            if '/git/ref/heads/main' in path: return {'object': {'sha': A}}
            if '/compare/' in path: return {'status': 'identical'}
            if '/releases?' in path: return [release]
            if '/releases/5/assets?' in path: return release['assets']
            if '/git/ref/tags/v1.2.3' in path: return {'object': {'type': 'commit', 'sha': A}}
            raise AssertionError(path)
        def bound_source_file(source, sha, path):
            self.assertEqual((source, sha), ('OtherOrg/alpha', A))
            return json.dumps(config() if path == 'web-publish.json' else
                              {'version': '1.2.3', 'channel': 'stable'}).encode()
        with patch.dict('os.environ', {'GITHUB_REPOSITORY': 'OtherOrg/alpha'}), \
             patch('publish.api', side_effect=fake_api), \
             patch('publish.source_file', side_effect=bound_source_file):
            resolved = resolve(self.root, 'alpha', '17', self.root / 'candidate.json')
        self.assertEqual((resolved['release_tag'], resolved['source_sha']), ('v1.2.3', A))

    def test_registered_stable_release_rejects_manifest_version_mismatch(self):
        catalog = read_json(self.root / 'catalog/sites.json')
        catalog['sites']['alpha'].pop('artifact')
        catalog['sites']['alpha'].update(release_asset='Game-{tag}-web.zip', accepted_release_channels=['prerelease', 'stable'],
                                         release_manifest_path='release/manifest.json')
        write_json(self.root / 'catalog/sites.json', catalog)
        run = {
            'conclusion': 'success', 'status': 'completed', 'event': 'workflow_dispatch',
            'head_branch': 'main', 'head_sha': A, 'path': '.github/workflows/verify.yml',
            'repository': {'full_name': 'OtherOrg/alpha'}, 'head_repository': {'full_name': 'OtherOrg/alpha'},
            'run_started_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:10:00Z',
        }
        release = {'id': 5, 'target_commitish': A, 'draft': False, 'prerelease': False,
                   'tag_name': 'v1.2.3', 'published_at': '2026-01-01T00:05:00Z', 'assets': []}
        def fake_api(path):
            if '/actions/runs/17' in path: return run
            if '/git/ref/heads/main' in path: return {'object': {'sha': A}}
            if '/compare/' in path: return {'status': 'identical'}
            if '/releases?' in path: return [release]
            raise AssertionError(path)
        def bound_source_file(source, sha, path):
            self.assertEqual((source, sha), ('OtherOrg/alpha', A))
            return json.dumps(config() if path == 'web-publish.json' else
                              {'version': '1.2.4', 'channel': 'stable'}).encode()
        with patch.dict('os.environ', {'GITHUB_REPOSITORY': 'OtherOrg/alpha'}), \
             patch('publish.api', side_effect=fake_api), \
             patch('publish.source_file', side_effect=bound_source_file):
            with self.assertRaisesRegex(ValueError, 'manifest version'):
                resolve(self.root, 'alpha', '17', self.root / 'candidate.json')

    def test_release_tag_must_resolve_to_tested_sha(self):
        catalog = read_json(self.root / 'catalog/sites.json')
        catalog['sites']['alpha'].pop('artifact')
        catalog['sites']['alpha']['release_asset'] = 'Game-{tag}-web.zip'
        write_json(self.root / 'catalog/sites.json', catalog)
        run = {
            'conclusion': 'success', 'status': 'completed', 'event': 'workflow_dispatch',
            'head_branch': 'main', 'head_sha': A, 'path': '.github/workflows/verify.yml',
            'repository': {'full_name': 'OtherOrg/alpha'}, 'head_repository': {'full_name': 'OtherOrg/alpha'},
            'run_started_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:10:00Z',
        }
        release = {'id': 5, 'target_commitish': A, 'draft': False, 'prerelease': True,
                   'tag_name': 'v1', 'published_at': '2026-01-01T00:05:00Z', 'assets': []}
        def fake_api(path):
            if '/actions/runs/17' in path: return run
            if '/git/ref/heads/main' in path: return {'object': {'sha': A}}
            if '/compare/' in path: return {'status': 'identical'}
            if '/releases?' in path: return [release]
            if '/git/ref/tags/v1' in path: return {'object': {'type': 'commit', 'sha': B}}
            raise AssertionError(path)
        with patch.dict('os.environ', {'GITHUB_REPOSITORY': 'OtherOrg/alpha'}), \
             patch('publish.api', side_effect=fake_api), \
             patch('publish.source_file', return_value=json.dumps(config()).encode()):
            with self.assertRaisesRegex(ValueError, 'tag does not resolve'):
                resolve(self.root, 'alpha', '17', self.root / 'candidate.json')


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
