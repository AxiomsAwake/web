#!/usr/bin/env python3
"""Publish bounded, immutable runner evidence; only marked expired outputs expire."""
import argparse
import contextlib
import fcntl
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time
import uuid

MARK = '.runner-evidence.json'
SCHEMA = 'axioms-runner-evidence-v1'


def require(value, message):
    if not value:
        raise ValueError(message)


def safe_path(path):
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        if part.exists() or part.is_symlink():
            require(not part.is_symlink(), f'symlink refused: {part}')
            require(part.is_dir(), f'non-directory ancestor: {part}')
    return path


def selection(parts, patterns):
    """Return whether this path matches, or may contain a match, without glob expansion."""
    if not patterns:
        return True, True
    possible = False
    for pattern in patterns:
        states = {0}
        for part in (*parts, None):
            for index in range(len(pattern)):
                if index in states and pattern[index] == '**':
                    states.add(index + 1)
            if len(pattern) in states:
                return True, True  # matched directory includes its descendants
            if part is None:
                possible |= bool(states)
                break
            states = {index if pattern[index] == '**' else index + 1
                      for index in states if index < len(pattern)
                      and (pattern[index] == '**' or fnmatch.fnmatchcase(part, pattern[index]))}
    return False, possible


def inventory(path, byte_cap, file_cap, copy_to=None, includes=None):
    """Stream selected entries; bound scanned names and actual copied/read bytes."""
    result, total, scanned, pending = {}, 0, 0, [path]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                src = Path(entry.path)
                rel = src.relative_to(path).as_posix()
                if rel == MARK:
                    continue
                scanned += 1
                require(scanned <= file_cap, 'file count or scanned entry limit exceeded')
                matched, descend = selection(tuple(rel.split('/')), includes)
                if not (matched or descend):
                    continue  # no stat/open/read inside unrelated subtrees
                mode = entry.stat(follow_symlinks=False).st_mode
                require(not stat.S_ISLNK(mode) or matched, 'symlink selection ancestor')
                if stat.S_ISDIR(mode):
                    result[rel + '/'] = [0, 'directory']
                    if copy_to:
                        (copy_to / rel).mkdir(parents=True, exist_ok=True)
                    pending.append(src)
                    continue
                if not matched:
                    continue
                fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, 'rb') as source:
                    require(stat.S_ISREG(os.fstat(source.fileno()).st_mode), f'non-regular file: {src}')
                    digest, size, dest = hashlib.sha256(), 0, None
                    if copy_to:
                        target = copy_to / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        dest = target.open('xb')
                    with contextlib.closing(dest) if dest else contextlib.nullcontext():
                        while True:
                            chunk = source.read(min(1024 * 1024, byte_cap - total + 1))
                            if not chunk:
                                break
                            size += len(chunk)
                            total += len(chunk)
                            require(total <= byte_cap, 'byte limit exceeded')
                            digest.update(chunk)
                            if dest:
                                dest.write(chunk)
                    result[rel] = [size, digest.hexdigest()]
    return result, total


def read_marker(path):
    marker = path / MARK
    require(not marker.is_symlink() and marker.is_file(), 'marker missing or symlinked')
    require(marker.stat().st_size <= 4 * 1024 * 1024, 'marker too large')
    with marker.open() as stream:
        data = json.load(stream)
    require(data.get('schema') == SCHEMA, 'unknown marker')
    require(isinstance(data.get('created'), (int, float)) and isinstance(data.get('expires'), (int, float)), 'invalid lifetime')
    return data


def write_marker(path, data):
    with (path / MARK).open('x') as stream:
        json.dump(data, stream, sort_keys=True)
    require((path / MARK).stat().st_size <= 4 * 1024 * 1024, 'marker too large')


def checked_output(path, repo, byte_cap, file_cap):
    require(path.is_dir() and not path.is_symlink(), 'unsafe managed directory')
    data = read_marker(path)
    require(data.get('repository') == repo and data.get('channel') == path.parent.name and data.get('kind') == 'published', 'wrong owner')
    require(path.name == f"{data.get('run')}-{data.get('attempt')}", 'identity mismatch')
    manifest, size = inventory(path, byte_cap, file_cap)
    require(manifest == data.get('files'), 'managed evidence changed; preserve it')
    return data, size + (path / MARK).stat().st_size


def publish(args):
    previous_mask = os.umask(0o077)
    try:
        return publish_private(args)
    finally:
        os.umask(previous_mask)


def publish_private(args):
    includes = getattr(args, 'include', []) or []
    require(len(includes) <= 100, 'too many include patterns')
    require(all(value and not value.startswith('/') and '\\' not in value
                and all(part not in ('', '.', '..', MARK) for part in value.split('/'))
                for value in includes), 'invalid include selection')
    args.includes = [tuple(value.split('/')) for value in includes]
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', args.channel), 'invalid channel')
    require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository or ''), 'invalid repository')
    require(all(p not in ('.', '..') for p in args.repository.split('/')), 'invalid repository segments')
    require(re.fullmatch(r'[1-9][0-9]*', args.run or '') and re.fullmatch(r'[1-9][0-9]*', args.attempt or ''), 'numeric run and attempt required')
    require(all(re.fullmatch(r'[1-9][0-9]*-[1-9][0-9]*', p) for p in args.pin), 'invalid pin')
    require(min(args.keep_previous, args.grace_days) >= 0 and min(args.max_run_bytes, args.max_total_bytes, args.max_files) > 0, 'invalid limits')
    source = safe_path(args.source)
    root = safe_path(args.evidence_root) if args.evidence_root else safe_path(args.cache_root) / 'axioms-evidence'
    require(source.is_dir(), 'source directory missing')
    owner = safe_path(root / args.repository / args.channel)
    require(not source.is_relative_to(owner) and not owner.is_relative_to(source), 'overlapping source and destination')
    require(not (source / MARK).exists() and not (source / MARK).is_symlink(), 'reserved source marker')
    owner.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(owner / '.writer.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, 'w') as lock:
        require(stat.S_ISREG(os.fstat(lock.fileno()).st_mode), 'unsafe lock')
        fcntl.flock(lock, fcntl.LOCK_EX)
        return publish_locked(args, source, owner)


def publish_locked(args, source, owner):
    now, current = time.time(), f'{args.run}-{args.attempt}'
    target, stage = owner / current, owner / ('.staging.' + uuid.uuid4().hex)
    grace = args.grace_days * 86400
    outputs, preserved, removed, protected_staging_bytes = [], [], [], 0
    for scanned_outputs, entry in enumerate(owner.iterdir()):
        require(scanned_outputs < args.max_files, 'owner entry limit exceeded; manual review required')
        if entry.name == '.writer.lock':
            continue
        try:
            if entry.name.startswith('.staging.'):
                require(entry.is_dir() and not entry.is_symlink(), 'unsafe staging')
                data = read_marker(entry)
                require(not entry.is_symlink() and data.get('repository') == args.repository and data.get('channel') == args.channel and data.get('kind') in ('staging', 'published') and data.get('stage') == entry.name, 'unowned staging')
                # A crash may leave both the staging marker and a pending final
                # manifest. Count protected partial copies against future quota.
                _, partial_bytes = inventory(entry, args.max_run_bytes + 4 * 1024 * 1024, args.max_files + 1)
                if now > data['expires'] and now - data['created'] > grace:
                    shutil.rmtree(entry)
                    removed.append(entry.name)
                else:
                    protected_staging_bytes += partial_bytes + (entry / MARK).stat().st_size
                continue
            data, size = checked_output(entry, args.repository, args.max_run_bytes, args.max_files)
            outputs.append((entry, data, size))
        except (OSError, ValueError, TypeError, KeyError):
            preserved.append(entry.name)
    require(not (target.exists() or target.is_symlink()) or any(p == target for p, _, _ in outputs), 'destination collision with unverified history')
    base = dict(schema=SCHEMA, repository=args.repository, channel=args.channel, source_commit=os.environ.get('GITHUB_SHA'), run=args.run, attempt=args.attempt, created=now, expires=now + grace, stage=stage.name)
    stage.mkdir()
    try:
        write_marker(stage, dict(base, kind='staging'))
        files, size = inventory(source, args.max_run_bytes, args.max_files, stage, args.includes)
        existing = next((d for p, d, _ in outputs if p == target), None)
        if existing:
            require(existing['files'] == files, 'immutable destination collision')
            return dict(destination=str(target), reused=True, removed=removed, preserved=preserved)
        pending = stage / ('.marker.' + uuid.uuid4().hex)
        with pending.open('x') as stream:
            json.dump(dict(base, kind='published', files=files), stream, sort_keys=True)
        require(pending.stat().st_size <= 4 * 1024 * 1024, 'marker too large')
        pending.replace(stage / MARK)
        size += (stage / MARK).stat().st_size
        require(size <= args.max_run_bytes, 'run limit includes marker')
        # Count/quota pressure never shortens the declared minimum evidence lifetime.
        ordered = sorted(outputs, key=lambda item: item[1]['created'], reverse=True)
        keep = {p.name for p, _, _ in ordered[:args.keep_previous]} | set(args.pin) | {current}
        eligible = [(p, d, n) for p, d, n in reversed(ordered) if p.name not in args.pin and now > d['expires'] and now - d['created'] > grace]
        total = sum(n for _, _, n in outputs) + protected_staging_bytes + size
        victims = []
        for p, _, n in eligible:
            if p.name not in keep or total > args.max_total_bytes:
                victims.append(p)
                total -= n
        require(total <= args.max_total_bytes, 'quota exhausted by protected evidence; publication refused')
        for victim in victims:
            # Recheck before deletion; unknown or modified data is never discarded.
            checked_output(victim, args.repository, args.max_run_bytes, args.max_files)
            shutil.rmtree(victim)
            removed.append(victim.name)
        stage.rename(target)
        return dict(destination=str(target), reused=False, removed=removed, preserved=preserved)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--cache-root', default=os.environ.get('RUNNER_TOOL_CACHE'))
    parser.add_argument('--evidence-root', help='use this root directly instead of CACHE/axioms-evidence')
    parser.add_argument('--channel', default='verification')
    parser.add_argument('--include', action='append', default=[], help='confined relative file/directory/glob; repeatable')
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY'))
    parser.add_argument('--run', default=os.environ.get('GITHUB_RUN_ID'))
    parser.add_argument('--attempt', default=os.environ.get('GITHUB_RUN_ATTEMPT'))
    parser.add_argument('--keep-previous', type=int, default=12)
    parser.add_argument('--grace-days', type=float, default=7)
    parser.add_argument('--max-run-bytes', type=int, default=256 * 1024 * 1024)
    parser.add_argument('--max-total-bytes', type=int, default=4 * 1024 * 1024 * 1024)
    parser.add_argument('--max-files', type=int, default=10000)
    parser.add_argument('--pin', action='append', default=[])
    args = parser.parse_args()
    try:
        require(bool(args.evidence_root or args.cache_root), '--evidence-root, --cache-root or RUNNER_TOOL_CACHE required')
        print(json.dumps(publish(args), sort_keys=True))
    except (OSError, ValueError, TypeError) as error:
        print(f'evidence publication/retention failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
