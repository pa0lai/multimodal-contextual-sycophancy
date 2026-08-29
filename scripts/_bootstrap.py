"""Shared bootstrap for direct script execution."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def add_repo_root_to_path() -> str:
    repo_root = str(Path(__file__).resolve().parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    return repo_root


REPO_ROOT = add_repo_root_to_path()
