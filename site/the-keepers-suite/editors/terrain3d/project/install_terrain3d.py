#!/usr/bin/env python3
"""Install pinned, unmodified MIT Terrain3D in a Godot project (Python 3.11+).

No account, elevation or shell commands. Existing unknown installs are never
replaced. A cached archive is hash-checked before every extraction.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import urllib.request
import zipfile

VERSION = "1.0.2-stable"
URL = f"https://github.com/TokisanGames/Terrain3D/releases/download/v{VERSION}/Terrain3D_v{VERSION}.zip"
SHA256 = "a071850250ec5e596aa54da61c01d75768774eb379ee997584d426a45f4884a2"
SIZE = 42312488
MARKER = ".axioms-install.json"


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def install(project: Path, archive: Path | None = None) -> Path:
    project = project.resolve()
    if not (project / "project.godot").is_file():
        raise ValueError("Target must contain project.godot")
    target = project / "addons" / "terrain_3d"
    if target.exists():
        marker = target / MARKER
        if marker.is_file():
            receipt = json.loads(marker.read_text())
            if receipt.get("archive_sha256") == SHA256 and all(
                (target / p).is_file() and digest(target / p) == sha
                for p, sha in receipt.get("files", {}).items()
            ) and receipt.get("files"):
                return target
        raise ValueError("Existing Terrain3D differs from the pinned install; move it aside explicitly first.")
    if archive is None:
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "axioms-tools"
        cache.mkdir(parents=True, exist_ok=True)
        archive = cache / f"terrain3d-{SHA256}.zip"
        if not archive.is_file() or archive.stat().st_size != SIZE or digest(archive) != SHA256:
            request = urllib.request.Request(URL, headers={"User-Agent": "AxiomsAwake-Terrain3D-Installer/1"})
            fd, name = tempfile.mkstemp(dir=cache, suffix=".download")
            try:
                with os.fdopen(fd, "wb") as out, urllib.request.urlopen(request, timeout=60) as response:
                    total = 0
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > SIZE:
                            raise ValueError("Archive exceeds pinned size")
                        out.write(chunk)
                candidate = Path(name)
                if candidate.stat().st_size != SIZE or digest(candidate) != SHA256:
                    raise ValueError("Terrain3D archive failed its pinned SHA-256/size check")
                candidate.replace(archive)
            finally:
                Path(name).unlink(missing_ok=True)
    if archive.stat().st_size != SIZE or digest(archive) != SHA256:
        raise ValueError("Terrain3D archive failed its pinned SHA-256/size check")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".terrain3d-", dir=target.parent) as scratch:
        stage = Path(scratch) / "terrain_3d"
        stage.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            total = 0
            seen = set()
            for info in bundle.infolist():
                parts = PurePosixPath(info.filename).parts
                if "terrain_3d" not in parts:
                    continue
                index = parts.index("terrain_3d")
                relative = PurePosixPath(*parts[index + 1:])
                if not relative.parts or info.is_dir():
                    continue
                if ".." in relative.parts or "\\" in str(relative) or relative.is_absolute() or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Unsafe archive path or symlink")
                if str(relative) in seen:
                    raise ValueError("Duplicate archive path")
                seen.add(str(relative))
                total += info.file_size
                if total > 512 * 1024 * 1024 or len(seen) > 5000:
                    raise ValueError("Expanded add-on exceeds install budget")
                destination = stage / str(relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as source, destination.open("wb") as out:
                    shutil.copyfileobj(source, out)
        if not list(stage.rglob("*.gdextension")):
            raise ValueError("Pinned archive did not contain a Terrain3D extension")
        files = {p.relative_to(stage).as_posix(): digest(p) for p in stage.rglob("*") if p.is_file()}
        (stage / MARKER).write_text(json.dumps({"version": VERSION, "archive_sha256": SHA256, "files": files}, indent=2) + "\n")
        stage.rename(target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--archive", type=Path, help="Use an already downloaded pinned ZIP; no network request")
    args = parser.parse_args()
    try:
        print(f"Terrain3D {VERSION}: {install(args.project, args.archive)}")
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Terrain3D installation failed: {exc}\n")


if __name__ == "__main__":
    main()
