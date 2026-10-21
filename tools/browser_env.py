#!/usr/bin/env python3
"""Prepare pinned Playwright; explicit browser-only mode owns its work cache.

Browser-only callers must already provide Chromium's OS libraries and renderer.
They retain the work directory while consumers are active, then remove it after
preserving unique evidence. Consumers must use the printed browser-cache path.
"""
import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time

VERSION = '1.57.0'


def ensure(work, *, local_browser_only=False):
    """Return the prepared Python path without changing the caller environment.

    The explicit local mode bypasses shared runner caches and OS package setup.
    Existing callers retain the ordinary-local or self-hosted setup behavior.
    """
    started = time.monotonic()
    shared = (
        not local_browser_only
        and os.environ.get('RUNNER_ENVIRONMENT') == 'self-hosted'
    )
    root = Path(os.environ['RUNNER_TOOL_CACHE']) / 'axioms-web' if shared else work
    child_options = {}
    if local_browser_only:
        root = Path(work).resolve()
        child_env = os.environ.copy()
        child_env['PLAYWRIGHT_BROWSERS_PATH'] = str(root / 'browsers')
        child_options['env'] = child_env
    root.mkdir(parents=True, exist_ok=True)
    key = f'python-{sys.version_info.major}.{sys.version_info.minor}-playwright-{VERSION}'
    environment = root / key
    python = environment / 'bin/python'
    lock = root / (key + '.lock')
    with lock.open('a') as stream:
        deadline = time.monotonic() + 120
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Browser environment is busy for over 120 seconds')
                time.sleep(0.2)
        probe = f"import importlib.metadata as m; assert m.version('playwright') == '{VERSION}'"
        ready = python.exists() and subprocess.run(
            [str(python), '-c', probe], capture_output=True, timeout=15,
            **child_options,
        ).returncode == 0
        if not ready:
            subprocess.run(
                [sys.executable, '-m', 'venv', str(environment)],
                check=True, timeout=30, **child_options,
            )
            subprocess.run(
                [str(python), '-m', 'pip', 'install',
                 '--disable-pip-version-check', '--no-input', '--timeout', '20',
                 '--retries', '2', f'playwright=={VERSION}'],
                check=True, timeout=180, **child_options,
            )
        args = [str(python), '-m', 'playwright', 'install']
        if not shared and not local_browser_only:
            args.append('--with-deps')
        subprocess.run(
            args + ['chromium'], check=True, timeout=240, **child_options,
        )
    elapsed = round(time.monotonic() - started, 3)
    disposition = 'reused' if ready else 'installed'
    print(
        f'Browser checker {disposition}; pinned Playwright {VERSION}; '
        f'preparation_seconds={elapsed}'
    )
    print(f'python={python}')
    if local_browser_only:
        print(f'PLAYWRIGHT_BROWSERS_PATH={root / "browsers"}')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write(
                f'python={python}\ncache_status={disposition}\n'
                f'preparation_seconds={elapsed}\n'
            )
    return python


def main(argv=None):
    """Parse the setup mode and prepare its explicitly owned work directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument(
        '--local-browser-only', action='store_true',
        help='Keep Python and Chromium under --work; skip OS package installation',
    )
    args = parser.parse_args(argv)
    ensure(args.work, local_browser_only=args.local_browser_only)


if __name__ == '__main__':
    main()
