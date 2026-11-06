from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_PROJECT_FILES = (
    "current-state.md",
    "architecture.md",
    "decisions.md",
    "README.md",
)


@dataclass(slots=True)
class ContextBundle:
    status: str
    root: Path | None
    text: str = ""
    files: tuple[str, ...] = ()
    total_chars: int = 0
    truncated: bool = False


def discover_context_root(
    configured_path: Path | None,
    roots: list[Path],
    config_path: Path,
) -> Path | None:
    # Context is opt-in and explicit: never discover a neighbouring private store.
    if configured_path is None:
        return None
    try:
        resolved = configured_path.expanduser().resolve(strict=True)
    except OSError:
        return None
    if resolved.is_dir() and (resolved / "AGENTS.md").is_file():
        return resolved
    return None


def _slug_variants(repo_name: str) -> tuple[str, ...]:
    camel = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", repo_name)
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", camel).strip("-").lower()
    compact = re.sub(r"[^a-z0-9]+", "", repo_name.lower())
    values = [repo_name.lower(), normalized, compact]
    return tuple(dict.fromkeys(value for value in values if value))


def _matches_repository_metadata(path: Path, repo_name: str) -> bool:
    try:
        prefix = path.read_text(encoding="utf-8")[:6_000]
    except (OSError, UnicodeError):
        return False

    target = repo_name.lower()
    for line in prefix.splitlines():
        if not line.lower().startswith("repository:"):
            continue
        value = line.split(":", 1)[1].strip().strip("'\"").lower()
        repo_part = value.rsplit("/", 1)[-1]
        if repo_part == target:
            return True
    return False


def find_project_dir(context_root: Path, repo_name: str) -> Path | None:
    projects = context_root / "projects"
    if not projects.is_dir():
        return None

    for variant in _slug_variants(repo_name):
        candidate = projects / variant
        if (
            candidate.is_dir()
            and not candidate.is_symlink()
            and candidate.resolve().is_relative_to(context_root.resolve())
        ):
            return candidate

    for candidate in projects.iterdir():
        if not candidate.is_dir() or candidate.is_symlink():
            continue
        current_state = candidate / "current-state.md"
        if current_state.is_file() and _matches_repository_metadata(current_state, repo_name):
            return candidate
    return None


def _append_file(
    context_root: Path,
    path: Path,
    remaining: int,
) -> tuple[str, str, bool]:
    relative = path.relative_to(context_root).as_posix()
    if path.is_symlink() or not path.resolve().is_relative_to(context_root.resolve()):
        return "", relative, False
    header = f"### Project context: {relative}\n\n"
    if remaining <= len(header):
        return "", relative, True

    try:
        content = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return "", relative, False

    available = remaining - len(header)
    truncated = len(content) > available
    if truncated:
        marker = "\n\n[context file truncated by Local LLM Code Auditor]"
        content = content[: max(0, available - len(marker))].rstrip() + marker
    return header + content, relative, truncated


def load_context(context_root: Path | None, repo_name: str, max_chars: int) -> ContextBundle:
    if context_root is None:
        return ContextBundle(status="UNAVAILABLE", root=None)

    candidates: list[Path] = []
    agents = context_root / "AGENTS.md"
    if agents.is_file():
        candidates.append(agents)

    project_dir = find_project_dir(context_root, repo_name)
    if project_dir is not None:
        candidates.extend(
            project_dir / name for name in _PROJECT_FILES if (project_dir / name).is_file()
        )

    sections: list[str] = []
    files: list[str] = []
    truncated = False
    remaining = max_chars

    for path in candidates:
        section, relative, file_truncated = _append_file(context_root, path, remaining)
        if not section:
            truncated = truncated or file_truncated
            break
        sections.append(section)
        files.append(relative)
        remaining -= len(section)
        truncated = truncated or file_truncated
        if remaining <= 0:
            break

    text = "\n\n".join(sections)
    return ContextBundle(
        status="LOADED" if text else "EMPTY",
        root=context_root,
        text=text,
        files=tuple(files),
        total_chars=len(text),
        truncated=truncated,
    )


def compose_llm_input(context: ContextBundle, evidence: str) -> str:
    if not context.text:
        return evidence
    return (
        "# Project context\n"
        "Durable guidance follows. On conflict, current live repository evidence has priority.\n\n"
        f"{context.text}\n\n"
        "# Live repository audit evidence\n\n"
        f"{evidence}"
    )
