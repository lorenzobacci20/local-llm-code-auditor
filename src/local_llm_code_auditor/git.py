from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

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

        if (root / ".git").exists():
            candidates.add(root)

        try:
            markers = root.rglob(".git")
            for marker in markers:
                repo_candidate = marker.parent
                if len(repo_candidate.parts) - base_depth > max_depth:
                    continue
                if _excluded_relative_path(repo_candidate, root, exclude_dir_globs):
                    continue
                candidates.add(repo_candidate)
        except OSError:
            pass

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

    status_args = ["git", "status", "--short"]
    if not include_untracked_names:
        status_args.append("--untracked-files=no")
    status = run(status_args, repo, 60).stdout.strip()

    unstaged = run(
        ["git", "diff", "--no-ext-diff", "--no-textconv", "--unified=3"], repo, 60
    ).stdout
    staged = run(
        ["git", "diff", "--cached", "--no-ext-diff", "--no-textconv", "--unified=3"], repo, 60
    ).stdout
    raw_diff = (unstaged + "\n" + staged).strip()
    diff_chars_original = len(raw_diff)
    diff_truncated = diff_chars_original > max_diff_chars
    diff = raw_diff
    if diff_truncated:
        diff = raw_diff[:max_diff_chars] + "\n\n[diff truncated by Local LLM Code Auditor]"

    recent_log = run(
        ["git", "log", "--since=24.hours", "--pretty=format:%h %ad %s", "--date=iso", "-n", "30"],
        repo,
        60,
    ).stdout.strip()

    branch_result = run(["git", "branch", "--show-current"], repo, 60)
    branch = branch_result.stdout.strip() or "(detached HEAD)"
    head = run(["git", "rev-parse", "--short=12", "HEAD"], repo, 60).stdout.strip() or "unknown"

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
