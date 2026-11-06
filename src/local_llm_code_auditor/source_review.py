from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from .git import DEFAULT_DISCOVERY_EXCLUDE_DIR_GLOBS
from .process import run

_SOURCE_EXTENSIONS = {
    ".cs",
    ".fs",
    ".vb",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".kt",
    ".kts",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".swift",
    ".vue",
    ".svelte",
}

_HIGH_SIGNAL_HINTS: tuple[tuple[str, int], ...] = (
    ("program.", 100),
    ("startup.", 100),
    ("authorization", 95),
    ("authentication", 95),
    ("security", 90),
    ("auth", 80),
    ("middleware", 75),
    ("controller", 70),
    ("endpoint", 70),
    ("handler", 65),
    ("service", 60),
    ("usecase", 60),
    ("repository", 60),
    ("dbcontext", 60),
    ("validator", 50),
    ("mapper", 45),
    ("profile", 40),
    ("worker", 40),
    ("hostedservice", 40),
    ("model", 25),
    ("entity", 25),
    ("domain", 25),
    ("api", 20),
)

_SOURCE_PATH_EXCLUDE_GLOBS = (
    "wwwroot/lib/*",
    "*/wwwroot/lib/*",
    "wwwroot/vendor/*",
    "*/wwwroot/vendor/*",
    "vendor/*",
    "*/vendor/*",
    "vendors/*",
    "*/vendors/*",
    "third_party/*",
    "*/third_party/*",
    "third-party/*",
    "*/third-party/*",
    "node_modules/*",
    "*/node_modules/*",
    ".yarn/*",
    "*/.yarn/*",
    ".pnpm/*",
    "*/.pnpm/*",
)

_GENERATED_FILE_GLOBS = (
    "*.min.js",
    "*.g.cs",
    "*.g.i.cs",
    "*.designer.cs",
    "*modelsnapshot.cs",
)

_CATEGORY_ORDER = (
    "entrypoint",
    "security",
    "api",
    "service",
    "data",
    "domain",
    "background",
    "validation",
    "other",
)

_CHARS_PER_TOKEN_ESTIMATE = 3.2


@dataclass(slots=True)
class SourceReview:
    enabled: bool
    files: tuple[str, ...] = ()
    text: str = ""
    chars_original: int = 0
    truncated: bool = False
    redacted_lines: int = 0
    budget_chars: int = 0
    candidate_count: int = 0
    categories: tuple[str, ...] = ()
    candidate_files: tuple[str, ...] = ()
    followup_files: tuple[str, ...] = ()

    def evidence_text(self) -> str:
        if not self.enabled:
            return "Source code review evidence: DISABLED"
        lines = [
            "Source code review evidence:",
            "Coverage: BOUNDED_SELECTED_SOURCE_FILES_NOT_WHOLE_REPOSITORY",
            "Selection strategy: CHANGED_FIRST_THEN_ARCHITECTURAL_DIVERSITY_WITH_OPTIONAL_TARGETED_FOLLOWUP",
            "Vendor/generated source: EXCLUDED_UNLESS_CHANGED_WHEN_APPLICABLE",
            "Source secret pre-redaction: DISABLED_LOCAL_OLLAMA_TRUST_BOUNDARY",
            "Confidentiality rule: source values may be inspected by the local model for security analysis, but secret values must never be quoted, reproduced, or written into the Markdown report.",
            "Review discipline: never claim that unselected source is defect-free or that there is no unreviewed critical logic.",
            "Review discipline: before reporting an input-validation or safety defect, check supplied nearby guards, allowlists, normalization, and counter-evidence.",
            "Review discipline: never claim two source artifacts are consistent/matching unless both required artifacts are actually present in the supplied source evidence or a deterministic analyzer explicitly established that relationship.",
            "Review discipline: omit candidate concerns that supplied evidence later disproves, shows to be intentional, acceptable, or already guarded.",
            "Review discipline: do not turn comments/documentation-only preferences into findings unless they hide a concrete correctness, security, operability, or maintenance risk.",
            "Review discipline: do not turn missing optional evidence into a generic action item unless it is material to a concrete finding or explicit release/deployment intent.",
            f"Source candidate files after filters: {self.candidate_count}",
            f"Source budget chars for this run: {self.budget_chars}",
            f"Source files selected: {len(self.files)}",
            "Source categories selected: "
            + (", ".join(self.categories) if self.categories else "none"),
            "Source follow-up files: "
            + (", ".join(self.followup_files) if self.followup_files else "none"),
            "Source files: " + (", ".join(self.files) if self.files else "none"),
            f"Source original chars before evidence bounding: {self.chars_original}",
            f"Source evidence truncated: {'YES' if self.truncated else 'NO'}",
        ]
        if self.text:
            lines.append(self.text)
        return "\n".join(lines)


def adaptive_source_budget(
    *,
    num_ctx: int,
    num_predict: int,
    base_prompt_chars: int,
    configured_max_chars: int,
) -> int:
    if configured_max_chars <= 0 or num_ctx <= 0:
        return 0
    safety_tokens = max(8_192, num_ctx // 8)
    available_input_tokens = max(0, num_ctx - num_predict - safety_tokens)
    target_prompt_chars = int(available_input_tokens * _CHARS_PER_TOKEN_ESTIMATE)
    available_chars = max(0, target_prompt_chars - max(0, base_prompt_chars))
    return min(configured_max_chars, available_chars)


def _excluded(path: Path, repo: Path, patterns: tuple[str, ...]) -> bool:
    try:
        parts = path.relative_to(repo).parts[:-1]
    except ValueError:
        return True
    return any(fnmatch(part.lower(), pattern.lower()) for part in parts for pattern in patterns)


def _git_paths(repo: Path, args: list[str]) -> tuple[str, ...]:
    result = run(["git", *args], repo, 60)
    if not result.ok:
        return ()
    return tuple(
        line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()
    )


def _changed_paths(repo: Path) -> set[str]:
    changed = set(_git_paths(repo, ["diff", "--name-only"]))
    changed.update(_git_paths(repo, ["diff", "--cached", "--name-only"]))
    changed.update(_git_paths(repo, ["ls-files", "--others", "--exclude-standard"]))
    return {item.lower() for item in changed}


def _source_specific_excluded(path: Path, repo: Path, changed: set[str]) -> bool:
    rel = path.relative_to(repo).as_posix()
    lowered = rel.lower()
    if any(fnmatch(lowered, pattern.lower()) for pattern in _SOURCE_PATH_EXCLUDE_GLOBS):
        return True

    if lowered not in changed:
        if any(fnmatch(path.name.lower(), pattern) for pattern in _GENERATED_FILE_GLOBS):
            return True
        if any(part.lower() == "migrations" for part in path.relative_to(repo).parts[:-1]):
            return True
    return False


def _candidate_paths(
    repo: Path,
    exclude_patterns: tuple[str, ...],
    changed: set[str],
) -> tuple[Path, ...]:
    tracked = set(_git_paths(repo, ["ls-files"]))
    untracked = set(_git_paths(repo, ["ls-files", "--others", "--exclude-standard"]))
    candidates: list[Path] = []
    for rel in sorted(tracked | untracked, key=str.lower):
        path = repo / rel
        if path.suffix.lower() not in _SOURCE_EXTENSIONS:
            continue
        if _excluded(path, repo, exclude_patterns):
            continue
        if _source_specific_excluded(path, repo, changed):
            continue
        if (
            path.is_file()
            and not path.is_symlink()
            and path.resolve().is_relative_to(repo.resolve())
        ):
            candidates.append(path)
    return tuple(candidates)


def _score(repo: Path, path: Path, changed: set[str]) -> tuple[int, str]:
    rel = path.relative_to(repo).as_posix()
    lowered = rel.lower()
    score = 1_000 if lowered in changed else 0
    for hint, weight in _HIGH_SIGNAL_HINTS:
        if hint in lowered:
            score += weight
    depth = len(Path(rel).parts)
    score += max(0, 12 - depth)
    return score, lowered


def _category(repo: Path, path: Path) -> str:
    lowered = path.relative_to(repo).as_posix().lower()
    name = path.name.lower()

    if name.startswith(("program.", "startup.")):
        return "entrypoint"
    if any(
        token in lowered
        for token in ("authorization", "authentication", "security", "auth", "middleware")
    ):
        return "security"
    if any(token in lowered for token in ("controller", "endpoint", "handler", "/api/")):
        return "api"
    if any(token in lowered for token in ("service", "usecase", "application/")):
        return "service"
    if any(token in lowered for token in ("repository", "dbcontext", "/data/", "database")):
        return "data"
    if any(
        token in lowered
        for token in ("models/", "model/", "entities/", "entity/", "domain/", "dto", "viewmodel")
    ):
        return "domain"
    if any(
        token in lowered for token in ("worker", "hostedservice", "background", "/jobs/", "/job/")
    ):
        return "background"
    if any(token in lowered for token in ("validator", "mapper", "mapping", "profile")):
        return "validation"
    return "other"


def _rank(repo: Path, paths: list[Path], changed: set[str]) -> list[Path]:
    return sorted(
        paths, key=lambda path: (-_score(repo, path, changed)[0], _score(repo, path, changed)[1])
    )


def _diverse_order(repo: Path, paths: list[Path], changed: set[str]) -> list[Path]:
    groups: dict[str, list[Path]] = {category: [] for category in _CATEGORY_ORDER}
    for path in _rank(repo, paths, changed):
        groups[_category(repo, path)].append(path)

    ordered: list[Path] = []
    while any(groups.values()):
        for category in _CATEGORY_ORDER:
            if groups[category]:
                ordered.append(groups[category].pop(0))
    return ordered


def _select_candidates(
    repo: Path,
    candidates: tuple[Path, ...],
    changed: set[str],
    max_files: int,
) -> list[Path]:
    if max_files <= 0:
        return []

    changed_paths = [
        path for path in candidates if path.relative_to(repo).as_posix().lower() in changed
    ]
    unchanged_paths = [
        path for path in candidates if path.relative_to(repo).as_posix().lower() not in changed
    ]
    ranked_changed = _rank(repo, changed_paths, changed)
    diverse_unchanged = _diverse_order(repo, unchanged_paths, changed)

    selected: list[Path] = []
    if ranked_changed and diverse_unchanged and max_files >= 4:
        architecture_reserve = min(4, max_files // 4)
        selected.extend(ranked_changed[: max_files - architecture_reserve])
        selected.extend(diverse_unchanged[:architecture_reserve])

        if len(selected) < max_files:
            remaining_changed = [path for path in ranked_changed if path not in selected]
            remaining_unchanged = [path for path in diverse_unchanged if path not in selected]
            selected.extend((remaining_changed + remaining_unchanged)[: max_files - len(selected)])
    elif ranked_changed:
        selected.extend(ranked_changed[:max_files])
    else:
        selected.extend(diverse_unchanged[:max_files])

    return selected[:max_files]


def _bounded_file(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    head = max(1, limit // 2)
    tail = max(1, limit - head)
    return (
        text[:head]
        + "\n\n[... source file middle truncated by Local LLM Code Auditor ...]\n\n"
        + text[-tail:],
        True,
    )


def _safe_candidate_path(repo: Path, rel: str, allowed: set[str]) -> Path | None:
    normalized = rel.strip().replace("\\", "/")
    if normalized not in allowed:
        return None
    path = (repo / normalized).resolve()
    try:
        path.relative_to(repo.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def collect(
    repo: Path,
    *,
    enabled: bool = True,
    max_chars: int = 96_000,
    max_files: int = 16,
    max_file_chars: int = 16_000,
    exclude_dir_globs: tuple[str, ...] = DEFAULT_DISCOVERY_EXCLUDE_DIR_GLOBS,
) -> SourceReview:
    if not enabled:
        return SourceReview(enabled=False)

    changed = _changed_paths(repo)
    candidates = _candidate_paths(repo, exclude_dir_globs, changed)
    selected_candidates = _select_candidates(repo, candidates, changed, max_files)

    selected: list[str] = []
    sections: list[str] = []
    categories: list[str] = []
    total_original = 0
    truncated = False
    used = 0

    for path in selected_candidates:
        if max_chars <= 0:
            truncated = bool(candidates)
            break
        if path.is_symlink() or not path.resolve().is_relative_to(repo.resolve()):
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        total_original += len(text)
        text, file_truncated = _bounded_file(text, max_file_chars)
        truncated = truncated or file_truncated

        rel = path.relative_to(repo).as_posix()
        block = f"\n--- SOURCE FILE: {rel} ---\n{text}\n--- END SOURCE FILE: {rel} ---"
        remaining = max_chars - used
        if remaining <= 0:
            truncated = True
            break
        if len(block) > remaining:
            block = block[:remaining] + "\n[... source evidence truncated by total budget ...]"
            truncated = True
        sections.append(block)
        selected.append(rel)
        category = _category(repo, path)
        if category not in categories:
            categories.append(category)
        used += len(block)
        if used >= max_chars:
            break

    candidate_files = tuple(path.relative_to(repo).as_posix() for path in candidates)
    return SourceReview(
        enabled=True,
        files=tuple(selected),
        text="\n".join(sections),
        chars_original=total_original,
        truncated=truncated,
        budget_chars=max_chars,
        candidate_count=len(candidates),
        categories=tuple(categories),
        candidate_files=candidate_files,
    )


def extend_with_followup(
    repo: Path,
    review: SourceReview,
    requested_files: tuple[str, ...],
    *,
    total_max_chars: int,
    max_file_chars: int,
) -> SourceReview:
    if not review.enabled or not requested_files:
        review.budget_chars = total_max_chars
        return review

    allowed = set(review.candidate_files)
    already = set(review.files)
    sections = [review.text] if review.text else []
    selected = list(review.files)
    followup: list[str] = []
    categories = list(review.categories)
    total_original = review.chars_original
    truncated = review.truncated
    used = len(review.text)

    for rel in requested_files:
        if rel in already:
            continue
        path = _safe_candidate_path(repo, rel, allowed)
        if path is None:
            continue
        remaining = total_max_chars - used
        if remaining <= 0:
            truncated = True
            break

        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        total_original += len(text)
        text, file_truncated = _bounded_file(text, max_file_chars)
        truncated = truncated or file_truncated

        canonical = path.relative_to(repo.resolve()).as_posix()
        block = f"\n--- FOLLOW-UP SOURCE FILE: {canonical} ---\n{text}\n--- END FOLLOW-UP SOURCE FILE: {canonical} ---"
        if len(block) > remaining:
            block = (
                block[:remaining]
                + "\n[... follow-up source evidence truncated by total budget ...]"
            )
            truncated = True
        sections.append(block)
        selected.append(canonical)
        followup.append(canonical)
        already.add(canonical)
        category = _category(repo.resolve(), path)
        if category not in categories:
            categories.append(category)
        used += len(block)
        if used >= total_max_chars:
            break

    return SourceReview(
        enabled=True,
        files=tuple(selected),
        text="\n".join(section for section in sections if section),
        chars_original=total_original,
        truncated=truncated,
        redacted_lines=review.redacted_lines,
        budget_chars=total_max_chars,
        candidate_count=review.candidate_count,
        categories=tuple(categories),
        candidate_files=review.candidate_files,
        followup_files=tuple(followup),
    )
