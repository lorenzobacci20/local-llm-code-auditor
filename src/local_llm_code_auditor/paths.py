"""Allow only ordinary files/directories below the explicitly selected root."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from fnmatch import fnmatch
from pathlib import Path

_SKIP_DIRS = {".git", "bin", "obj", "node_modules", ".venv", "venv"}

# Mask a whole file before any head/tail sampling. Drop oversized inputs instead
# of processing a secret whose delimiters might lie outside a partial read.
MAX_EVIDENCE_FILE_BYTES = 2 * 1024 * 1024


def read_evidence_file(path: Path) -> bytes | None:
    with path.open("rb") as source:
        data = source.read(MAX_EVIDENCE_FILE_BYTES + 1)
    return data if len(data) <= MAX_EVIDENCE_FILE_BYTES else None


def local_path(root: Path, path: Path, *, directory: bool = False) -> bool:
    try:
        parts = path.relative_to(root).parts
        if not parts or ".." in parts:
            return False
        current = root
        for part in parts:
            current /= part
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or (
                getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            ):
                return False
        return stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    except (OSError, ValueError):
        return False


def repository_files(root: Path, pattern: str) -> Iterator[Path]:
    for folder, dirs, names in os.walk(root, followlinks=False):
        parent = Path(folder)
        dirs[:] = [
            name
            for name in dirs
            if name.lower() not in _SKIP_DIRS and local_path(root, parent / name, directory=True)
        ]
        for name in names:
            path = parent / name
            if fnmatch(name, pattern) and local_path(root, path):
                yield path
