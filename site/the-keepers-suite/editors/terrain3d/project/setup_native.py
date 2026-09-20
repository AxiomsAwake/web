#!/usr/bin/env python3
"""Install verified native libraries without replacing authored project files."""
from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path
import shutil
import tempfile


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parent
    if not (root/'project.godot').is_file():
        raise ValueError('Run this from the extracted native project')
    spec = importlib.util.spec_from_file_location('terrain_install', root/'install_terrain3d.py')
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    destination = root/'addons/terrain_3d/bin'
    if destination.is_symlink():
        raise ValueError('Library directory must not be a symbolic link')
    with tempfile.TemporaryDirectory(prefix='axioms-native-editor-') as temporary:
        addon = Path(installer.install(Path(temporary)))
        files = [p for p in (addon/'bin').iterdir() if p.is_file() and p.suffix.lower() in ('.dll', '.so', '.dylib')]
        if not files:
            raise ValueError('Verified release contains no native libraries')
        for source in files:
            target = destination/source.name
            if target.is_symlink() or (target.exists() and digest(target) != digest(source)):
                raise ValueError('Different library already exists: ' + source.name)
        destination.mkdir(parents=True, exist_ok=True)
        for source in files:
            target = destination/source.name
            if not target.exists():
                staged = target.with_name(target.name + '.candidate')
                if staged.exists():
                    raise ValueError('Inspect interrupted copy: ' + staged.name)
                shutil.copyfile(source, staged)
                if digest(staged) != digest(source):
                    staged.unlink()
                    raise ValueError('Library copy failed verification')
                staged.rename(target)
    print('Open project.godot with Godot 4.7.2. Authored scenes, materials, regions and plugin source were not replaced.')


if __name__ == '__main__':
    main()
