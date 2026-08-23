#!/usr/bin/env python3
"""Verify RELEASE_MANIFEST.json completeness, sizes, and SHA-256 hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

try:
    from _bootstrap import REPO_ROOT
except ModuleNotFoundError:
    from scripts._bootstrap import REPO_ROOT


IGNORED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "multimodal_contextual_sycophancy.egg-info"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_files(root: Path) -> dict[str, Path]:
    files = {}
    for path in root.rglob("*"):
        if not path.is_file() or IGNORED_PARTS.intersection(path.parts):
            continue
        relative = path.relative_to(root).as_posix()
        if relative == "RELEASE_MANIFEST.json":
            continue
        files[relative] = path
    return files


def verify(root: Path | str = REPO_ROOT) -> None:
    root = Path(root)
    manifest = json.loads((root / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    expected = {entry["path"]: entry for entry in manifest["release_files"]}
    actual = candidate_files(root)
    if set(expected) != set(actual):
        missing = sorted(set(expected) - set(actual))
        unlisted = sorted(set(actual) - set(expected))
        raise SystemExit(f"Manifest file-set mismatch: missing={missing} unlisted={unlisted}")
    failures = []
    for relative, path in actual.items():
        entry = expected[relative]
        if path.stat().st_size != entry["byte_size"] or sha256(path) != entry["sha256"]:
            failures.append(relative)
    if failures:
        raise SystemExit(f"Manifest hash/size mismatch: {failures}")
    print(f"PASS release manifest: files={len(actual)}")


if __name__ == "__main__":
    verify()

