from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from local_llm_code_auditor.git import (
    RepositoryPathError,
    discover_repositories,
    resolve_repository,
)


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_resolve_repository_accepts_nested_directory(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", cwd=repo)
    nested = repo / "src" / "feature"
    nested.mkdir(parents=True)

    assert resolve_repository(nested) == repo.resolve()


def test_resolve_repository_rejects_missing_path(tmp_path: Path):
    missing = tmp_path / "missing"

    with pytest.raises(RepositoryPathError, match="does not exist"):
        resolve_repository(missing)


def test_resolve_repository_rejects_file(tmp_path: Path):
    file_path = tmp_path / "not-a-directory.txt"
    file_path.write_text("x", encoding="utf-8")

    with pytest.raises(RepositoryPathError, match="not a directory"):
        resolve_repository(file_path)


def test_discovery_ignores_invalid_root_git_marker_and_keeps_valid_children(tmp_path: Path):
    # Reproduce a configured container such as C:\\Projects with a stale `.git`
    # marker that is not itself a valid Git repository.
    (tmp_path / ".git").mkdir()

    child = tmp_path / "SampleApp"
    child.mkdir()
    _git("init", cwd=child)

    discovered = discover_repositories([tmp_path])

    assert discovered == [child.resolve()]
    assert tmp_path.resolve() not in discovered


def test_discovery_normalizes_nested_working_tree_candidates(tmp_path: Path):
    child = tmp_path / "repo"
    child.mkdir()
    _git("init", cwd=child)
    nested = child / "src"
    nested.mkdir()

    assert discover_repositories([tmp_path]) == [child.resolve()]
