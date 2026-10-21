#!/usr/bin/env python3
"""Check setup policy with mocked children; never install or launch anything."""
import fcntl
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import browser_env


class BrowserEnvironmentTests(unittest.TestCase):
    """Own disposable lock fixtures and observe the actual child requests."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='web-browser-env-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.work = self.root / 'work'
        self.tool_cache = self.root / 'shared'
        self.environment = {
            'RUNNER_TOOL_CACHE': str(self.tool_cache),
            'PLAYWRIGHT_BROWSERS_PATH': '/unrelated-browser-cache',
        }
        self.output = io.StringIO()
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, self.environment, clear=True).start()
        patch('sys.stdout', self.output).start()
        self.run = patch.object(browser_env.subprocess, 'run').start()
        self.run.return_value = subprocess.CompletedProcess([], 0)

    def prepared_python(self, root):
        key = (
            f'python-{browser_env.sys.version_info.major}.'
            f'{browser_env.sys.version_info.minor}-playwright-1.57.0'
        )
        return root / key / 'bin/python'

    def assert_install(self, expected_root, *, with_deps):
        python = self.prepared_python(expected_root)
        calls = self.run.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(
            calls[0].args[0],
            [browser_env.sys.executable, '-m', 'venv', str(python.parent.parent)],
        )
        self.assertEqual(calls[1].args[0], [
            str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
            '--no-input', '--timeout', '20', '--retries', '2',
            'playwright==1.57.0',
        ])
        install = [str(python), '-m', 'playwright', 'install']
        if with_deps:
            install.append('--with-deps')
        self.assertEqual(calls[2].args[0], install + ['chromium'])
        self.assertEqual([c.kwargs['timeout'] for c in calls], [30, 180, 240])
        self.assertTrue(all(c.kwargs['check'] for c in calls))
        return calls

    def test_ordinary_default_keeps_work_and_system_dependencies(self):
        result = browser_env.ensure(self.work)
        self.assertEqual(result, self.prepared_python(self.work))
        calls = self.assert_install(self.work, with_deps=True)
        self.assertTrue(all('env' not in call.kwargs for call in calls))
        self.assertFalse(self.tool_cache.exists())

    def test_self_hosted_default_keeps_shared_cache_without_system_install(self):
        os.environ['RUNNER_ENVIRONMENT'] = 'self-hosted'
        root = self.tool_cache / 'axioms-web'
        self.assertEqual(browser_env.ensure(self.work), self.prepared_python(root))
        calls = self.assert_install(root, with_deps=False)
        self.assertTrue(all('env' not in call.kwargs for call in calls))
        self.assertFalse(self.work.exists())

    def test_explicit_local_mode_owns_every_child_environment_on_both_hosts(self):
        for runner in ['github-hosted', 'self-hosted']:
            with self.subTest(runner=runner):
                os.environ['RUNNER_ENVIRONMENT'] = runner
                before = dict(os.environ)
                self.run.reset_mock()
                result = browser_env.ensure(self.work, local_browser_only=True)
                self.assertEqual(result, self.prepared_python(self.work))
                calls = self.assert_install(self.work, with_deps=False)
                for call in calls:
                    self.assertEqual(call.kwargs['env'], {
                        **before,
                        'PLAYWRIGHT_BROWSERS_PATH': str(self.work / 'browsers'),
                    })
                    self.assertIsNot(call.kwargs['env'], os.environ)
                self.assertEqual(dict(os.environ), before)
                self.assertFalse(self.tool_cache.exists())

    def test_explicit_self_hosted_mode_does_not_require_shared_cache_variable(self):
        os.environ['RUNNER_ENVIRONMENT'] = 'self-hosted'
        del os.environ['RUNNER_TOOL_CACHE']
        browser_env.ensure(self.work, local_browser_only=True)
        self.assert_install(self.work, with_deps=False)

    def test_reuse_probes_exact_pin_and_preserves_output_contract(self):
        python = self.prepared_python(self.work)
        python.parent.mkdir(parents=True)
        python.touch()
        output_file = self.root / 'github-output'
        os.environ['GITHUB_OUTPUT'] = str(output_file)
        before = dict(os.environ)
        self.assertEqual(
            browser_env.ensure(self.work, local_browser_only=True), python,
        )
        probe, install = self.run.call_args_list
        self.assertEqual(probe.args[0], [
            str(python), '-c',
            "import importlib.metadata as m; assert m.version('playwright') == '1.57.0'",
        ])
        self.assertEqual(probe.kwargs['timeout'], 15)
        self.assertTrue(probe.kwargs['capture_output'])
        self.assertEqual(install.args[0], [
            str(python), '-m', 'playwright', 'install', 'chromium',
        ])
        for call in [probe, install]:
            self.assertEqual(
                call.kwargs['env']['PLAYWRIGHT_BROWSERS_PATH'],
                str(self.work / 'browsers'),
            )
        fields = dict(line.split('=', 1) for line in output_file.read_text().splitlines())
        self.assertEqual(set(fields), {'python', 'cache_status', 'preparation_seconds'})
        self.assertEqual(fields['python'], str(python))
        self.assertEqual(fields['cache_status'], 'reused')
        self.assertGreaterEqual(float(fields['preparation_seconds']), 0)
        self.assertIn(f'python={python}\n', self.output.getvalue())
        self.assertIn(
            f'PLAYWRIGHT_BROWSERS_PATH={self.work / "browsers"}\n',
            self.output.getvalue(),
        )
        self.assertEqual(dict(os.environ), before)

    def test_non_github_caller_gets_usable_absolute_paths(self):
        relative = Path(os.path.relpath(self.work))
        result = browser_env.ensure(relative, local_browser_only=True)
        self.assertTrue(result.is_absolute())
        self.assertIn(f'python={result}\n', self.output.getvalue())
        self.assertIn(str(self.work / 'browsers'), self.output.getvalue())

    def test_failed_child_propagates_and_releases_real_lock(self):
        for failed_child in range(3):
            with self.subTest(failed_child=failed_child):
                before = dict(os.environ)
                failure = subprocess.CalledProcessError(7, ['controlled-child'])
                self.run.reset_mock()
                self.run.side_effect = (
                    [subprocess.CompletedProcess([], 0)] * failed_child + [failure]
                )
                with self.assertRaises(subprocess.CalledProcessError) as caught:
                    browser_env.ensure(self.work, local_browser_only=True)
                self.assertIs(caught.exception, failure)
                self.assertEqual(self.run.call_count, failed_child + 1)
                lock = next(self.work.glob('*.lock'))
                with lock.open('a') as stream:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertEqual(dict(os.environ), before)

    def test_child_timeout_propagates_and_releases_real_lock(self):
        timeout = subprocess.TimeoutExpired(['controlled-child'], 240)
        self.run.side_effect = [
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
            timeout,
        ]
        with self.assertRaises(subprocess.TimeoutExpired) as caught:
            browser_env.ensure(self.work, local_browser_only=True)
        self.assertIs(caught.exception, timeout)
        with next(self.work.glob('*.lock')).open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_busy_lock_retains_120_second_deadline_and_starts_no_child(self):
        python = self.prepared_python(self.work)
        self.work.mkdir()
        lock = self.work / (python.parent.parent.name + '.lock')
        with lock.open('a') as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(browser_env.time, 'monotonic', side_effect=[0, 0, 119, 120]):
                with patch.object(browser_env.time, 'sleep') as sleep:
                    with self.assertRaisesRegex(TimeoutError, '120 seconds'):
                        browser_env.ensure(self.work, local_browser_only=True)
                    sleep.assert_called_once_with(0.2)
        self.run.assert_not_called()
        with lock.open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_wrong_existing_pin_is_repaired_before_browser_download(self):
        python = self.prepared_python(self.work)
        python.parent.mkdir(parents=True)
        python.touch()
        self.run.side_effect = [
            subprocess.CompletedProcess([], 1),
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
        ]
        browser_env.ensure(self.work, local_browser_only=True)
        self.assertEqual(self.run.call_count, 4)
        self.assertEqual(self.run.call_args_list[2].args[0][-1], 'playwright==1.57.0')
        self.assertEqual(self.run.call_args_list[3].args[0][-2:], ['install', 'chromium'])

    def test_cli_forwards_explicit_mode_and_preserves_default_api(self):
        with patch.object(browser_env, 'ensure') as ensure:
            browser_env.main(['--work', str(self.work), '--local-browser-only'])
            ensure.assert_called_once_with(self.work, local_browser_only=True)
            ensure.reset_mock()
            browser_env.main(['--work', str(self.work)])
            ensure.assert_called_once_with(self.work, local_browser_only=False)


if __name__ == '__main__':
    unittest.main()
