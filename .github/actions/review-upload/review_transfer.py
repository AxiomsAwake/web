#!/usr/bin/env python3
"""Stage explicit diagnostic files, never packages or whole repository archives."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

MAX_BYTES = 16 * 1024 * 1024
MAX_FILES = 96
EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.mp4', '.webm', '.json', '.log', '.txt'}
PREFIX = 'axioms-review-transfer-'


def inside(path, roots):
    return any(path.is_relative_to(root.resolve()) for root in roots)


def stage(root, patterns, temp, allowed_roots, *, limit=MAX_BYTES, file_limit=MAX_FILES):
    """Copy unchanged allowlisted files to a new, disposable, bounded directory."""
    root, temp = Path(root), Path(temp).resolve()
    allowed_roots = [Path(path) for path in allowed_roots]
    if root.is_symlink() or not root.is_dir() or not inside(root.resolve(), allowed_roots):
        raise ValueError('Review directory must be inside this job workspace or temporary directory')
    root = root.resolve()
    if any(root == path.resolve() for path in allowed_roots):
        raise ValueError('Select a report subdirectory, not a whole workspace or temporary root')
    if not 0 < limit <= MAX_BYTES or not 0 < file_limit <= MAX_FILES:
        raise ValueError('Transfer bounds cannot exceed the fixed policy')
    patterns = [value.strip() for value in patterns.splitlines() if value.strip()]
    if not patterns or len(patterns) > 16:
        raise ValueError('Specify 1 to 16 relative report patterns')
    selected = {}
    for pattern in patterns:
        parts = Path(pattern).parts
        if Path(pattern).is_absolute() or '\\' in pattern or any(p in ('.', '..') or p.startswith('.') for p in parts):
            raise ValueError('Patterns must be relative and exclude hidden and parent paths')
        for file in root.glob(pattern):
            if file.is_symlink() or not file.resolve().is_relative_to(root):
                raise ValueError('Symlinks and escaping report paths are not transferable')
            if not file.is_file():
                continue
            relative = file.relative_to(root)
            if relative.as_posix() == 'transfer-manifest.json':
                raise ValueError('Reserved transfer manifest name; narrow the requested patterns')
            if any(part.startswith('.') for part in relative.parts) or file.suffix.lower() not in EXTENSIONS:
                raise ValueError('Pattern selected an unsupported or hidden file; narrow the request')
            if any(parent.is_symlink() for parent in file.parents if parent != root):
                raise ValueError('Symlinked report ancestors are not transferable')
            selected[relative.as_posix()] = file
            if len(selected) > file_limit:
                return {'ready': False, 'reason': 'file_budget', 'files': len(selected)}
    if not selected:
        return {'ready': False, 'reason': 'no_files', 'files': 0}
    total = sum(file.stat().st_size for file in selected.values())
    if total > limit:
        return {'ready': False, 'reason': 'byte_budget', 'files': len(selected), 'bytes': total}
    destination = Path(tempfile.mkdtemp(prefix=PREFIX, dir=temp))
    manifest = {'schema': 'axioms-review-transfer/v1', 'source': os.environ.get('GITHUB_SHA'), 'files': []}
    try:
        copied = 0
        for name, file in sorted(selected.items()):
            # Check actual bytes, not only a possibly stale stat result.
            with file.open('rb') as stream:
                data = stream.read(limit - copied + 1)
            copied += len(data)
            if copied > limit:
                raise ValueError('Report grew beyond its transfer budget while staging')
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            manifest['files'].append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        encoded = (json.dumps(manifest, indent=2) + '\n').encode()
        if copied + len(encoded) > limit:
            shutil.rmtree(destination)
            return {'ready': False, 'reason': 'byte_budget', 'files': len(selected), 'bytes': copied + len(encoded)}
        (destination / 'transfer-manifest.json').write_bytes(encoded)
        return {'ready': True, 'directory': str(destination), 'files': len(selected), 'bytes': copied + len(encoded)}
    except Exception:
        shutil.rmtree(destination)
        raise


def cleanup(directory, temp):
    if not directory:
        return
    path = Path(directory)
    if path.is_symlink() or path.parent.resolve() != Path(temp).resolve() or not path.name.startswith(PREFIX):
        raise ValueError('Refusing to remove anything except this transfer staging directory')
    shutil.rmtree(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cleanup')
    args = parser.parse_args()
    temp = Path(os.environ['RUNNER_TEMP'])
    if args.cleanup is not None:
        cleanup(args.cleanup, temp)
        return
    result = stage(Path(os.environ['REVIEW_DIRECTORY']), os.environ['REVIEW_PATTERNS'], temp,
                   [Path(os.environ['GITHUB_WORKSPACE']), temp])
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write('ready=' + str(result['ready']).lower() + '\n')
        if result['ready']:
            output.write('directory=' + result['directory'] + '\n')
    print('REVIEW_TRANSFER_STAGE ' + json.dumps(result))


if __name__ == '__main__':
    main()
