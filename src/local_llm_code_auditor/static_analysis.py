from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_SKIP_PARTS = {".git", "bin", "obj", "node_modules", ".venv", "venv"}


@dataclass(frozen=True, slots=True)
class StaticFinding:
    analyzer: str
    severity: str
    code: str
    path: str
    message: str

    def render(self) -> str:
        return f"- {self.severity} [{self.code}] `{self.path}`: {self.message}"


def is_ignored_path(path: Path) -> bool:
    return path.is_symlink() or any(part.lower() in _SKIP_PARTS for part in path.parts)


def relative_path(repo: Path, path: Path) -> str:
    """Render analyzer paths portably so reports/tests are identical across OSes."""
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return path.as_posix()
