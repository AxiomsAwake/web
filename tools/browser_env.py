#!/usr/bin/env python3
"""Reuse the pinned checker environment on ordinary-user Linux runners."""
import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time

VERSION = '1.57.0'


def ensure(work):
    started = time.monotonic()
    shared = os.environ.get('RUNNER_ENVIRONMENT') == 'self-hosted'
    root = Path(os.environ['RUNNER_TOOL_CACHE']) / 'axioms-web' if shared else work
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
        ready = python.exists() and subprocess.run([str(python), '-c', probe], capture_output=True, timeout=15).returncode == 0
        if not ready:
            subprocess.run([sys.executable, '-m', 'venv', str(environment)], check=True, timeout=30)
            subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input',
                            '--timeout', '20', '--retries', '2', f'playwright=={VERSION}'], check=True, timeout=180)
        args = [str(python), '-m', 'playwright', 'install']
        if not shared:
            args.append('--with-deps')
        subprocess.run(args + ['chromium'], check=True, timeout=240)
    elapsed = round(time.monotonic() - started, 3)
    disposition = 'reused' if ready else 'installed'
    print(f'Browser checker {disposition}; pinned Playwright {VERSION}; preparation_seconds={elapsed}')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write(f'python={python}\ncache_status={disposition}\npreparation_seconds={elapsed}\n')
    return python


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    ensure(parser.parse_args().work)
