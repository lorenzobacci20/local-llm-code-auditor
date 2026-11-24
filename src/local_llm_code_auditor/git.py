from __future__ import annotations

import os
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from .paths import local_path
from .privacy import redact
from .process import run

DEFAULT_DISCOVERY_EXCLUDE_DIR_GLOBS: tuple[str, ...] = (
    "deploy",
    "deploy-*",
    "publish",
    "bin",
    "obj",
    "artifacts",
    "dist",
    "out",
    "backup",
    "archive",
)


class RepositoryPathError(ValueError):
    """Raised when a requested repository path cannot be used safely."""


@dataclass(slots=True)
class RepoSnapshot:
    path: Path
    status: str
    diff: str
    recent_log: str
    branch: str
    head: str
    diff_chars_original: int
    diff_truncated: bool


def resolve_repository(path: Path) -> Path:
    """Validate a path and normalize it to the containing Git repository root."""
    candidate = path.expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise RepositoryPathError(f"path does not exist: {candidate}") from exc
    except OSError as exc:
        raise RepositoryPathError(f"cannot resolve path {candidate}: {exc}") from exc

    if not resolved.is_dir():
        raise RepositoryPathError(f"path is not a directory: {resolved}")

    result = run(["git", "rev-parse", "--show-toplevel"], resolved, 60)
    if not result.ok:
        detail = (result.stderr or result.stdout).strip()
        suffix = f" ({detail})" if detail else ""
        raise RepositoryPathError(f"path is not inside a Git repository: {resolved}{suffix}")

    root_text = result.stdout.strip()
    if not root_text:
        raise RepositoryPathError(f"Git returned an empty repository root for: {resolved}")

    root = Path(root_text)
    if not root.is_absolute():
        root = resolved / root
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise RepositoryPathError(f"Git repository root is not accessible: {root}: {exc}") from exc

    if not root.is_dir():
        raise RepositoryPathError(f"Git repository root is not a directory: {root}")
    return root


def _excluded_relative_path(path: Path, root: Path, patterns: tuple[str, ...]) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(fnmatch(part.lower(), pattern.lower()) for part in parts for pattern in patterns)


def discover_repositories(
    roots: list[Path],
    max_depth: int = 4,
    exclude_dir_globs: tuple[str, ...] = DEFAULT_DISCOVERY_EXCLUDE_DIR_GLOBS,
) -> list[Path]:
    """Discover only Git-valid repositories below configured roots.

    A directory or file named `.git` is only a discovery hint. Every candidate is
    validated with `git rev-parse` before it can enter the audit set. Invalid or
    stale `.git` markers are ignored and never prevent valid child repositories
    from being discovered. Known deploy/build-output directory names are skipped
    by default so generated copies do not produce duplicate audits.
    """
    repos: set[Path] = set()
    for configured_root in roots:
        try:
            root = configured_root.expanduser().resolve(strict=True)
        except OSError:
            continue
        if not root.is_dir():
            continue

        base_depth = len(root.parts)
        candidates: set[Path] = set()

        for folder, dirs, files in os.walk(root, followlinks=False):
            parent = Path(folder)
            marker = parent / ".git"
            if (".git" in dirs and local_path(root, marker, directory=True)) or (
                ".git" in files and local_path(root, marker)
            ):
                candidates.add(parent)
            if len(parent.parts) - base_depth >= max_depth:
                dirs.clear()
                continue
            dirs[:] = [
                name
                for name in dirs
                if name != ".git"
                and not _excluded_relative_path(parent / name, root, exclude_dir_globs)
                and local_path(root, parent / name, directory=True)
            ]

        for candidate in candidates:
            if candidate != root and _excluded_relative_path(candidate, root, exclude_dir_globs):
                continue
            try:
                resolved_repo = resolve_repository(candidate)
            except RepositoryPathError:
                continue

            try:
                relative_depth = len(resolved_repo.relative_to(root).parts)
            except ValueError:
                continue
            if relative_depth > max_depth:
                continue
            if resolved_repo != root and _excluded_relative_path(
                resolved_repo, root, exclude_dir_globs
            ):
                continue
            repos.add(resolved_repo)

    return sorted(repos)


def snapshot(repo: Path, max_diff_chars: int, include_untracked_names: bool = True) -> RepoSnapshot:
    repo = resolve_repository(repo)

    def checked(args: list[str]) -> str:
        result = run(["git", *args], repo, 60)
        if not result.ok:
            raise RepositoryPathError(f"Git {args[0]} failed (exit {result.returncode})")
        return result.stdout

    status_args = ["status", "--short", "--ignore-submodules=all"]
    if not include_untracked_names:
        status_args.append("--untracked-files=no")
    status = redact(checked(status_args).rstrip())

    diff_args = ["--no-ext-diff", "--no-textconv", "--ignore-submodules=all", "--unified=3"]
    unstaged = checked(["diff", *diff_args])
    staged = checked(["diff", "--cached", *diff_args])
    raw_diff = (unstaged + "\n" + staged).strip()
    diff_chars_original = len(raw_diff)
    diff = redact(raw_diff)
    diff_truncated = len(diff) > max_diff_chars
    if diff_truncated:
        diff = diff[:max_diff_chars]

    branch = redact(checked(["branch", "--show-current"]).strip()) or "(detached HEAD)"
    # Git log exits nonzero on a repository with an unborn branch.
    head_result = run(["git", "rev-parse", "--verify", "--quiet", "--short=12", "HEAD"], repo, 60)
    if head_result.returncode not in {0, 1}:
        raise RepositoryPathError(f"Git rev-parse failed (exit {head_result.returncode})")
    head = head_result.stdout.strip() or "unborn"
    recent_log = ""
    if head_result.ok:
        recent_log = redact(
            checked(
                [
                    "log",
                    "--no-show-signature",
                    "--since=24.hours",
                    "--pretty=format:%h %ad %s",
                    "--date=iso",
                    "-n",
                    "30",
                ]
            ).strip()
        )

    return RepoSnapshot(
        path=repo,
        status=status,
        diff=diff,
        recent_log=recent_log,
        branch=branch,
        head=head,
        diff_chars_original=diff_chars_original,
        diff_truncated=diff_truncated,
    )
