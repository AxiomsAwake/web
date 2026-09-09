#!/usr/bin/env python3
"""Static publication contract. Standard library only; never executes payload code."""
from __future__ import annotations
import hashlib
import html
import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = 1
MAX_FILE = 90 * 1024 * 1024
MAX_SITE = 250 * 1024 * 1024
MAX_TOTAL = 900 * 1024 * 1024
ID = re.compile(r"[a-z][a-z0-9-]{0,47}\Z")
SHA = re.compile(r"[a-f0-9]{40}\Z")
HASHED = re.compile(r"assets/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.[a-f0-9]{8,64}\.[A-Za-z0-9]+\Z")
RESERVED = {"__release.json"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(), f"Missing or unsafe JSON: {path.name}")
    require(path.stat().st_size <= 8 * 1024 * 1024, "JSON exceeds limit")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def safe_name(name: str) -> str:
    require(isinstance(name, str) and bool(name), "Empty path")
    require(not any(c in name for c in ("\\", "\x00", "\n", "\r", ":", "?", "#", "%")), "Unsafe path characters")
    p = PurePosixPath(name)
    require(not p.is_absolute() and all(x not in ("", ".", "..") for x in name.split("/")), "Path escapes publication")
    require(not any(x.startswith(".") and x != ".nojekyll" for x in p.parts), "Hidden files are not public by default")
    require(not any(x.lower() in {"node_modules", "__pycache__"} for x in p.parts), "Development cache is not public")
    require(p.suffix.lower() not in {".pem", ".key", ".p12", ".pfx", ".map"}, "Secret/source-map extension is not public")
    require(name not in RESERVED, "Reserved publisher filename")
    return name


def rows(root: Path) -> list[dict]:
    require(root.is_dir() and not root.is_symlink(), "Payload must be a real directory")
    out = []
    total = 0
    for p in sorted(root.rglob("*")):
        require(not p.is_symlink(), "Payload symlinks are forbidden")
        name = p.relative_to(root).as_posix()
        safe_name(name)
        if p.is_dir():
            continue
        require(p.is_file(), "Special files are forbidden")
        size = p.stat().st_size
        require(size <= MAX_FILE, f"File exceeds 90 MiB: {name}; do not use LFS pointers for Pages")
        total += size
        require(total <= MAX_SITE and len(out) < 5000, "Site exceeds publication budget")
        data = p.read_bytes()
        require(not data.startswith(b"version https://git-lfs.github.com/spec/"), "LFS pointers cannot serve runtime assets")
        out.append({"path": name, "bytes": size, "sha256": hashlib.sha256(data).hexdigest()})
    require(any(r["path"] == "index.html" for r in out), "Public output needs index.html")
    return out


def digest(files: list[dict]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def registry(repo: Path) -> dict:
    value = read_json(repo / "catalog/sites.json")
    require(value.get("schema") == SCHEMA, "Unsupported registry schema")
    sites = value.get("sites", {})
    require(isinstance(sites, dict) and bool(sites), "Empty registry")
    for key, entry in sites.items():
        require(bool(ID.fullmatch(key)), "Invalid site id")
        require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", entry.get("producer", "")) is not None, "Invalid producer")
        require(isinstance(entry.get("enabled"), bool), "enabled must be explicit")
        require(re.fullmatch(r"\.github/workflows/[A-Za-z0-9_-]+\.ya?ml", entry.get("workflow", "")) is not None, "Invalid source workflow")
    return sites


def stage(artifact: Path, config: dict, target: Path) -> list[dict]:
    """Explicit mappings only; files not selected from a mixed archive never leave it."""
    require(config.get("schema") == SCHEMA and config.get("enabled") is True, "Publication not enabled in source config")
    require(not target.exists(), "Stage into a new directory")
    require(artifact.is_dir() and not artifact.is_symlink(), "Missing artifact directory")
    target.mkdir(parents=True)
    mappings = config.get("files", [])
    require(isinstance(mappings, list) and bool(mappings), "No approved files")
    try:
        for mapping in mappings:
            src_name, dst_name = mapping["from"], mapping["to"]
            for name in (src_name, dst_name):
                if name != ".":
                    safe_name(name)
            source = artifact if src_name == "." else artifact / src_name
            dest = target if dst_name == "." else target / dst_name
            require(source.exists() and not source.is_symlink(), f"Missing selected output: {src_name}")
            require(source.resolve().is_relative_to(artifact.resolve()), "Selected file escapes artifact")
            # Check every parent as well, including selected files beneath a symlink.
            require(not any(x.is_symlink() for x in [source, *source.parents] if x.is_relative_to(artifact)), "Symlink parent")
            if source.is_dir():
                for p in source.rglob("*"):
                    require(not p.is_symlink(), "Selected tree contains a symlink")
                    if p.is_file():
                        output = dest / p.relative_to(source)
                        safe_name(output.relative_to(target).as_posix())
                        require(not output.exists(), "Overlapping output mappings")
                        output.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(p, output)
            else:
                require(not dest.exists(), "Overlapping output mappings")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
        return rows(target)
    except Exception:
        shutil.rmtree(target)
        raise


def validate_state(repo: Path, site_id: str, state: dict) -> None:
    require(state.get("schema") == SCHEMA and state.get("site") == site_id, "Invalid release record")
    if not state.get("active"):
        require(not (repo / "site" / site_id).exists(), "Unpublished site still has files")
        return
    files, retained = state["files"], state.get("retained", [])
    require(digest(files) == state["digest"], "Release digest mismatch")
    expected = sorted(files + retained, key=lambda r: r["path"])
    require(len({r['path'] for r in expected}) == len(expected), "Duplicate manifest paths")
    require(rows(repo / "site" / site_id) == expected, f"Release bytes differ: {site_id}")


def decide(old: dict | None, candidate: dict, compare) -> str:
    if old and old.get("suspended"):
        return "suspended"
    watermark = (old or {}).get("watermark")
    if not watermark:
        return "publish"
    sha = candidate["source_sha"]
    if sha == watermark:
        if old.get("source_sha") != sha or not old.get("active"):
            return "superseded"  # An explicit restore/unpublish wins over old queued jobs.
        require(old["digest"] == candidate["digest"], "Different bytes for the same source SHA; make a new source commit")
        return "unchanged"
    relation = compare(watermark, sha)
    if relation == "ahead":
        return "publish"
    if relation == "behind":
        return "superseded"
    raise ValueError("Diverged source history; deliberately resolve the release instead of overwriting it")


def install(repo: Path, site_id: str, payload: Path, candidate: dict, old: dict | None) -> dict:
    destination = repo / "site" / site_id
    files = rows(payload)
    require(digest(files) == candidate["digest"], "Payload changed after validation")
    retained: dict[str, bytes] = {}
    if candidate.get("retain_hashed_assets") and old and old.get("active"):
        validate_state(repo, site_id, old)
        names = {r["path"] for r in files}
        for item in old["files"]:  # Exactly one previous generation, not its retained files.
            name = item["path"]
            if HASHED.fullmatch(name) and name not in names:
                retained[name] = (destination / name).read_bytes()
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(payload, destination)
    retained_rows = []
    for name, data in retained.items():
        p = destination / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        retained_rows.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    state = dict(candidate, schema=SCHEMA, site=site_id, active=True, suspended=False,
                 watermark=candidate["source_sha"], files=files, retained=sorted(retained_rows, key=lambda r: r['path']))
    write_json(repo / "releases" / f"{site_id}.json", state)
    validate_state(repo, site_id, state)
    return state


def assemble(repo: Path, output: Path, commit: str) -> dict:
    sites = registry(repo)
    require(output.resolve() != repo.resolve() and not repo.resolve().is_relative_to(output.resolve()), "Unsafe output directory")
    require(not output.is_symlink(), "Unsafe output symlink")
    source = repo / "site"
    require(not output.resolve().is_relative_to(source.resolve()), "Cannot assemble inside input")
    if source.exists():
        require(not source.is_symlink(), "Unsafe site directory")
        for p in source.iterdir():
            require(p.name in sites and p.is_dir() and not p.is_symlink(), "Unregistered file/folder in site/")
    release_dir = repo / "releases"
    if release_dir.exists():
        require(not release_dir.is_symlink(), "Unsafe releases directory")
        for p in release_dir.iterdir():
            require(p.name.endswith('.json') and p.stem in sites and not p.is_symlink(), "Unregistered release")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    deployment = {"schema": SCHEMA, "commit": commit, "sites": {}}
    cards = []
    total = 0
    for site_id, entry in sites.items():
        record = release_dir / f"{site_id}.json"
        if not record.exists():
            require(not (source / site_id).exists(), f"Files without release metadata: {site_id}")
            continue
        state = read_json(record)
        validate_state(repo, site_id, state)
        if not state.get("active"):
            continue
        require(entry['enabled'], f"Disable by unpublishing first: {site_id}")
        total += sum(r["bytes"] for r in state["files"] + state.get("retained", []))
        require(total <= MAX_TOTAL, "Assembled site exceeds 900 MiB budget")
        shutil.copytree(source / site_id, output / site_id)
        public = {k: state.get(k) for k in ("site", "source_sha", "digest", "watermark", "run_id")}
        public['deployment_commit'] = commit
        write_json(output / site_id / "__release.json", public)
        deployment["sites"][site_id] = public
        cards.append(f'<article><small>{html.escape(entry.get("kind", "game"))}</small><h2>{html.escape(entry["title"])}</h2><p>{html.escape(entry.get("description", ""))}</p><a href="./{site_id}/">Open {html.escape(entry["title"])} <span aria-hidden="true">→</span></a></article>')
    template = (repo / "catalog/index.html").read_text(encoding="utf-8")
    empty = '<p class="empty">The catalogue is being prepared. Games appear here after their first successful publication.</p>'
    (output / "index.html").write_text(template.replace("<!-- CARDS -->", "\n".join(cards) or empty), encoding="utf-8")
    (output / ".nojekyll").write_text("")
    (output / "404.html").write_text('<!doctype html><meta name="viewport" content="width=device-width"><title>Not found</title><h1>This page is not available.</h1><p>Return to the Axioms Awake catalogue.</p>')
    write_json(output / "deployment.json", deployment)
    return dict(deployment, bytes=total)
