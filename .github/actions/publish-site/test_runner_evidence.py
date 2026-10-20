import argparse
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import runner_evidence as evidence


class RetentionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / 'source'
        self.source.mkdir()
        (self.source / 'result.txt').write_text('unique evidence')
        self.owner = self.base / 'cache/axioms-evidence/owner/repo/verification'
        self.args = argparse.Namespace(source=self.source, cache_root=self.base / 'cache',
            repository='owner/repo', channel='verification', evidence_root=None, run='1', attempt='1', pin=[], keep_previous=1,
            grace_days=7, max_run_bytes=4096, max_total_bytes=32768, max_files=100)

    def publish(self, run, now=1000000):
        self.args.run = str(run)
        with patch.object(evidence.time, 'time', return_value=now):
            return evidence.publish(self.args)

    def test_publish_and_verified_immutable_retry(self):
        (self.source / 'empty').mkdir()
        result = self.publish(1)
        self.assertEqual(Path(result['destination']).joinpath('result.txt').read_text(), 'unique evidence')
        self.assertTrue((self.owner / '1-1/empty').is_dir())
        self.assertTrue(self.publish(1)['reused'])
        (self.source / 'result.txt').write_text('different')
        with self.assertRaisesRegex(ValueError, 'immutable'):
            self.publish(1)
        self.assertEqual((self.owner / '1-1/result.txt').read_text(), 'unique evidence')

    def test_private_output_even_with_permissive_caller_mask(self):
        previous = os.umask(0)
        try:
            self.publish(1)
        finally:
            restored = os.umask(previous)
        self.assertEqual(restored, 0)
        self.assertEqual((self.owner / '1-1').stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.owner / '1-1/result.txt').stat().st_mode & 0o777, 0o600)

    def test_expired_count_cleanup_preserves_unknown_pin_and_young(self):
        self.publish(1)
        self.publish(2)
        unknown = self.owner / 'legacy-history'
        unknown.mkdir()
        (unknown / 'unique.txt').write_text('preserve')
        self.args.pin = ['1-1']
        result = self.publish(3, now=2000000)
        self.assertTrue((self.owner / '1-1').exists())
        self.assertTrue((self.owner / '2-1').exists())  # newest previous retained
        self.assertIn('legacy-history', result['preserved'])
        self.args.pin = []
        result = self.publish(4, now=2000001)
        self.assertEqual(set(result['removed']), {'1-1', '2-1'})
        self.assertTrue((self.owner / '3-1').exists())  # grace cannot be shortened
        self.assertTrue(unknown.exists())

    def test_protected_quota_refuses_growth_without_eviction(self):
        self.publish(1)
        self.args.max_total_bytes = 600
        with self.assertRaisesRegex(ValueError, 'protected evidence'):
            self.publish(2)
        self.assertTrue((self.owner / '1-1').exists())
        self.assertFalse((self.owner / '2-1').exists())
        self.assertEqual(list(self.owner.glob('.staging.*')), [])

    def test_expired_quota_eviction(self):
        self.publish(1)
        self.args.max_total_bytes = 600
        result = self.publish(2, now=2000000)
        self.assertEqual(result['removed'], ['1-1'])
        self.assertTrue((self.owner / '2-1').exists())

    def test_source_symlinks_and_special_files_rejected(self):
        (self.source / 'link').symlink_to(self.source / 'result.txt')
        with self.assertRaises(OSError):
            self.publish(1)
        (self.source / 'link').unlink()
        import os
        os.mkfifo(self.source / 'fifo')
        with self.assertRaisesRegex(ValueError, 'non-regular'):
            self.publish(1)

    def test_output_and_ancestor_symlinks_are_never_followed(self):
        self.publish(1)
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'keep').write_text('keep')
        (self.owner / '2-1').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'collision'):
            self.publish(2)
        self.assertEqual((outside / 'keep').read_text(), 'keep')
        (self.base / 'redirect').symlink_to(self.base / 'cache', target_is_directory=True)
        self.args.cache_root = self.base / 'redirect'
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.publish(3)

    def test_changed_managed_files_or_extra_directory_preserved(self):
        self.publish(1)
        (self.owner / '1-1/new-empty').mkdir()
        self.args.keep_previous = 0
        result = self.publish(2, now=2000000)
        self.assertIn('1-1', result['preserved'])
        self.assertTrue((self.owner / '1-1/new-empty').exists())

    def test_oversized_modified_output_is_preserved_with_bounded_reads(self):
        self.publish(1)
        modified = self.owner / '1-1/result.txt'
        modified.write_bytes(b'x' * 100000)
        real_open = evidence.os.fdopen
        observed = []

        class ObservedReader:
            def __init__(self, wrapped):
                self.wrapped = wrapped
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.wrapped.close()
            def fileno(self):
                return self.wrapped.fileno()
            def read(self, limit):
                chunk = self.wrapped.read(limit)
                observed.append(len(chunk))
                return chunk

        def tracked_open(fd, mode):
            return ObservedReader(real_open(fd, mode))

        with patch.object(evidence.os, 'fdopen', side_effect=tracked_open):
            with self.assertRaisesRegex(ValueError, 'byte limit'):
                evidence.checked_output(self.owner / '1-1', 'owner/repo', 4096, 100)
        self.assertLessEqual(sum(observed), 4097)
        self.args.keep_previous = 0
        result = self.publish(2, now=2000000)
        self.assertIn('1-1', result['preserved'])
        self.assertEqual(modified.stat().st_size, 100000)

    def test_byte_limit_and_entry_limit_rollback(self):
        self.args.max_run_bytes = 2
        with self.assertRaisesRegex(ValueError, 'byte limit'):
            self.publish(1)
        self.assertEqual(list(self.owner.glob('.staging.*')), [])
        self.args.max_run_bytes = 4096
        self.args.max_files = 1
        (self.source / 'extra').write_text('x')
        with self.assertRaisesRegex(ValueError, 'file count'):
            self.publish(1)

    def test_owned_expired_staging_only(self):
        self.publish(1)
        for name, kind in [('.staging.owned', 'staging'), ('.staging.crashed', 'published')]:
            stage = self.owner / name
            stage.mkdir()
            evidence.write_marker(stage, dict(schema=evidence.SCHEMA, repository='owner/repo', channel='verification',
                created=1, expires=2, stage=name, kind=kind))
            (stage / 'partial').write_text('partial')
        unknown = self.owner / '.staging.unknown'
        unknown.mkdir()
        (unknown / 'unmarked').write_text('preserve')
        result = self.publish(2)
        self.assertEqual(set(result['removed']), {'.staging.owned', '.staging.crashed'})
        self.assertTrue(unknown.exists())

    def test_interrupted_young_staging_counts_against_quota(self):
        self.publish(1)
        stage = self.owner / '.staging.interrupted'
        stage.mkdir()
        evidence.write_marker(stage, dict(schema=evidence.SCHEMA, repository='owner/repo', channel='verification',
            created=1000000, expires=2000000, stage=stage.name, kind='staging'))
        (stage / 'partial').write_bytes(b'x' * 2048)
        self.args.max_total_bytes = 2048
        with self.assertRaisesRegex(ValueError, 'protected evidence'):
            self.publish(2, now=1000001)
        self.assertTrue((stage / 'partial').exists())
        self.assertFalse((self.owner / '2-1').exists())

    def test_confined_includes_prune_unrelated_and_copy_overlap_once(self):
        docs = self.source / 'docs'
        (docs / 'screenshots').mkdir(parents=True)
        (docs / 'screenshots/small.png').write_bytes(b'picture')
        (docs / 'platform-a.json').write_text('{}')
        (docs / 'large-unrelated.bin').write_bytes(b'x' * 100000)
        (self.source / '.git').mkdir()
        (self.source / '.git/huge').write_bytes(b'x' * 100000)
        (docs / 'unrelated-link').symlink_to(self.source / '.git', target_is_directory=True)
        self.args.include = ['docs/screenshots', 'docs/screenshots/*', 'docs/platform-*.json']
        opened = []
        original_open = evidence.os.open
        def tracked_open(path, *args, **kwargs):
            opened.append(str(path))
            return original_open(path, *args, **kwargs)
        with patch.object(evidence.os, 'open', side_effect=tracked_open):
            result = self.publish(1)
        output = Path(result['destination'])
        self.assertEqual((output / 'docs/screenshots/small.png').read_bytes(), b'picture')
        self.assertEqual((output / 'docs/platform-a.json').read_text(), '{}')
        self.assertFalse((output / '.git').exists())
        self.assertFalse((output / 'docs/large-unrelated.bin').exists())
        self.assertFalse(any('huge' in name or 'unrelated' in name for name in opened))
        self.assertEqual(sum(name.endswith('small.png') for name in opened), 1)
        self.assertTrue(self.publish(1)['reused'])

    def test_include_escapes_rejected_and_recursive_glob_supported(self):
        for selection in ['', '/absolute', '../escape', 'docs/../escape', '.',
                          'docs//file', '.runner-evidence.json', 'docs/.runner-evidence.json']:
            self.args.include = [selection]
            with self.assertRaisesRegex(ValueError, 'include'):
                self.publish(1)
        (self.source / 'docs/deep').mkdir(parents=True)
        (self.source / 'docs/deep/result.json').write_text('{}')
        self.args.include = ['docs/**/*.json']
        result = self.publish(1)
        self.assertTrue((Path(result['destination']) / 'docs/deep/result.json').exists())
        (self.source / 'linked').symlink_to(self.source / 'docs', target_is_directory=True)
        self.args.include = ['linked/deep/result.json']
        with self.assertRaisesRegex(ValueError, 'symlink selection ancestor'):
            self.publish(2)

    def test_include_scan_is_bounded_even_for_unmatched_names(self):
        self.args.max_files = 2
        (self.source / 'unmatched-a').write_text('x')
        (self.source / 'unmatched-b').write_text('x')
        self.args.include = ['missing-*']
        with self.assertRaisesRegex(ValueError, 'scanned entry'):
            self.publish(1)
        self.assertFalse((self.owner / '1-1').exists())

    def test_explicit_root_and_independent_channel(self):
        self.args.evidence_root = self.base / 'shared'
        self.args.channel = 'job-a'
        first = self.publish(1)
        self.args.channel = 'job-b'
        second = self.publish(1)
        self.assertEqual(Path(first['destination']), self.base / 'shared/owner/repo/job-a/1-1')
        self.assertNotEqual(first['destination'], second['destination'])
        self.args.channel = '../escape'
        with self.assertRaisesRegex(ValueError, 'channel'):
            self.publish(1)

    def test_concurrent_writer_waits_for_owner_lock(self):
        import fcntl
        import subprocess
        import sys
        self.owner.mkdir(parents=True)
        with (self.owner / '.writer.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            child = subprocess.Popen([sys.executable, str(Path(evidence.__file__)),
                str(self.source), '--cache-root', str(self.base / 'cache'),
                '--repository', 'owner/repo', '--run', '1', '--attempt', '1'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    child.communicate(timeout=0.1)
                self.assertFalse((self.owner / '1-1').exists())
                fcntl.flock(lock, fcntl.LOCK_UN)
                stdout, stderr = child.communicate(timeout=5)
                self.assertEqual(child.returncode, 0, stderr)
                self.assertEqual(json.loads(stdout)['destination'], str(self.owner / '1-1'))
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate()

    def test_expiry_is_persisted_and_repository_escape_rejected(self):
        self.publish(1)
        self.args.grace_days = 0
        self.args.keep_previous = 0
        self.publish(2, now=1000010)
        self.assertTrue((self.owner / '1-1').exists())
        for repo in ['../escape', 'owner/..', '/absolute', 'a/b/c']:
            self.args.repository = repo
            with self.assertRaisesRegex(ValueError, 'repository'):
                self.publish(3)


if __name__ == '__main__':
    unittest.main()
