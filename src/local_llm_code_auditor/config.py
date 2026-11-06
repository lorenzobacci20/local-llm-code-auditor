from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .git import DEFAULT_DISCOVERY_EXCLUDE_DIR_GLOBS


@dataclass(slots=True)
class AgentConfig:
    roots: list[Path] = field(default_factory=list)
    report_dir: Path = Path("reports")
    model: str = "qwen3.5:9b"
    think: bool | None = None
    ollama_url: str = "http://127.0.0.1:11434"
    num_ctx: int = 65_536
    num_predict: int = 8_192
    max_diff_chars: int = 120_000
    max_command_output_chars: int = 24_000
    command_timeout_seconds: int = 900
    llm_timeout_seconds: int = 3_600
    include_untracked_names: bool = True
    discovery_exclude_dirs: tuple[str, ...] = DEFAULT_DISCOVERY_EXCLUDE_DIR_GLOBS
    context_enabled: bool = False
    context_path: Path | None = None
    context_max_chars: int = 24_000
    source_review_enabled: bool = True
    source_review_max_chars: int = 96_000
    source_review_max_files: int = 16
    source_review_max_file_chars: int = 16_000
    source_review_followup_enabled: bool = True
    source_review_followup_max_files: int = 8
    source_review_followup_max_chars: int = 48_000
    source_review_critic_enabled: bool = True


def _positive_int(section: dict, key: str, default: int) -> int:
    value = int(section.get(key, default))
    if value <= 0:
        raise ValueError(f"{key} must be > 0")
    return value


def _optional_path(value: object, base_dir: Path) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    result = Path(str(value)).expanduser()
    if not result.is_absolute():
        result = base_dir / result
    return result.resolve()


def _string_tuple(section: dict, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = section.get(key)
    if raw is None:
        return default
    if not isinstance(raw, list):
        raise ValueError(f"{key} must be an array of strings")
    values = tuple(str(value).strip() for value in raw if str(value).strip())
    return values


def load_config(path: Path) -> AgentConfig:
    with path.open("rb") as fh:
        raw = tomllib.load(fh)

    agent = raw.get("agent", {})
    think = agent.get("think")
    if think is not None and not isinstance(think, bool):
        raise ValueError("think must be a boolean when configured")
    context = raw.get("context", {})
    source_review = raw.get("source_review", {})
    base_dir = path.expanduser().resolve().parent
    return AgentConfig(
        roots=[_optional_path(p, base_dir) for p in agent.get("roots", [])],
        report_dir=_optional_path(agent.get("report_dir", "reports"), base_dir),
        model=agent.get("model", "qwen3.5:9b"),
        think=think,
        ollama_url=agent.get("ollama_url", "http://127.0.0.1:11434").rstrip("/"),
        num_ctx=_positive_int(agent, "num_ctx", 65_536),
        num_predict=_positive_int(agent, "num_predict", 8_192),
        max_diff_chars=_positive_int(agent, "max_diff_chars", 120_000),
        max_command_output_chars=_positive_int(agent, "max_command_output_chars", 24_000),
        command_timeout_seconds=_positive_int(agent, "command_timeout_seconds", 900),
        llm_timeout_seconds=_positive_int(agent, "llm_timeout_seconds", 3_600),
        include_untracked_names=bool(agent.get("include_untracked_names", True)),
        discovery_exclude_dirs=_string_tuple(
            agent, "discovery_exclude_dirs", DEFAULT_DISCOVERY_EXCLUDE_DIR_GLOBS
        ),
        context_enabled=bool(context.get("enabled", False)),
        context_path=_optional_path(context.get("path"), base_dir),
        context_max_chars=_positive_int(context, "max_chars", 24_000),
        source_review_enabled=bool(source_review.get("enabled", True)),
        source_review_max_chars=_positive_int(source_review, "max_chars", 96_000),
        source_review_max_files=_positive_int(source_review, "max_files", 16),
        source_review_max_file_chars=_positive_int(source_review, "max_file_chars", 16_000),
        source_review_followup_enabled=bool(source_review.get("followup_enabled", True)),
        source_review_followup_max_files=_positive_int(source_review, "followup_max_files", 8),
        source_review_followup_max_chars=_positive_int(source_review, "followup_max_chars", 48_000),
        source_review_critic_enabled=bool(source_review.get("critic_enabled", True)),
    )
