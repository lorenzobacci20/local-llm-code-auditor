from __future__ import annotations

import json
import re

from .source_review import SourceReview

FOLLOWUP_SYSTEM_PROMPT = """You are selecting additional source files for a read-only local code audit.
Do not perform the final audit and do not suggest commands.
You are given current audit evidence, the source files already reviewed, and an allowlisted inventory of additional source files from the same Git repository.
Select only files whose contents are likely to materially reduce uncertainty around concrete correctness, security, authorization, data-flow, persistence, error-handling, concurrency, API-contract, or regression risks.
Prefer files directly related to code already reviewed, dependencies invoked by reviewed code, and architectural layers missing from the current sample.
Do not select files merely for broader coverage.
Return a JSON array of repository-relative file paths and nothing else.
Every returned path must appear exactly in the supplied allowlist.
Return [] when no additional file is likely to materially improve the audit."""


CRITIC_SYSTEM_PROMPT = """You are the final evidence verifier for a local nightly software audit.
You receive the complete audit evidence plus a draft audit written by another model pass.
Return a corrected final audit, not commentary about the draft.

Use only supplied evidence. Preserve concrete, supported defects and risks, but aggressively remove noise.
Mandatory rules:
- Remove any candidate finding whose own evidence or explanation concludes that it is correct, intentional, acceptable, harmless, already guarded, or \"no issue\".
- Remove comments/documentation-only suggestions unless they address a demonstrated correctness, security, operability, or material maintainability risk.
- Remove generic \"ensure\", \"check\", \"consider\", \"verify\", or \"add tests\" actions unless they map to a concrete supplied finding or explicit release/deployment intent.
- Do not repeat healthy telemetry (successful build, analyzer count zero, etc.) as multiple findings unless it materially affects the verdict.
- Never infer that unreviewed source is defect-free.
- Never claim two artifacts match or are consistent unless both are present in evidence or a deterministic analyzer established the relationship.
- Never infer database applied/pending migration state from static EF artifacts.
- Never recommend database mutation, push, merge, or deployment.
- A LOW finding must still describe a real defect, risk, or material maintainability problem. Pure style preferences are not findings.
- If a draft concern is contradicted by supplied guards, allowlists, normalization, or other counter-evidence, remove it.
- Do not invent new evidence.

Return concise Markdown with exactly these headings:
## Verdict
## Findings
## Suggested actions

Verdict must be GO, WARNING, or STOP.
If there are no actionable defects, Findings may contain one INFO statement saying no actionable defects were established in the reviewed evidence.
Every suggested action must correspond to a retained finding."""


def remaining_inventory(review: SourceReview) -> tuple[str, ...]:
    selected = set(review.files)
    return tuple(path for path in review.candidate_files if path not in selected)


def followup_user_prompt(current_llm_input: str, review: SourceReview, max_files: int) -> str:
    inventory = remaining_inventory(review)
    rendered = "\n".join(f"- {path}" for path in inventory) if inventory else "none"
    return (
        current_llm_input
        + "\n\n--- FOLLOW-UP FILE SELECTION ---\n"
        + f"Files already reviewed ({len(review.files)}): "
        + (", ".join(review.files) if review.files else "none")
        + "\n"
        + f"Select at most {max_files} additional files.\n"
        + "ALLOWLISTED REMAINING SOURCE FILES:\n"
        + rendered
    )


def _json_array_from_text(content: str) -> list[object] | None:
    stripped = content.strip()
    candidates = [stripped]
    match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", stripped, re.IGNORECASE)
    if match:
        candidates.insert(0, match.group(1))
    bracket = re.search(r"(\[[\s\S]*\])", stripped)
    if bracket:
        candidates.append(bracket.group(1))

    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            return value
    return None


def parse_followup_files(
    content: str,
    *,
    allowed_files: tuple[str, ...],
    already_selected: tuple[str, ...],
    max_files: int,
) -> tuple[str, ...]:
    if max_files <= 0:
        return ()

    values = _json_array_from_text(content)
    if values is None:
        return ()

    allowed_by_lower = {path.lower(): path for path in allowed_files}
    selected_lower = {path.lower() for path in already_selected}
    result: list[str] = []

    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip().replace("\\", "/")
        if not normalized or normalized.startswith("/") or ".." in normalized.split("/"):
            continue
        canonical = allowed_by_lower.get(normalized.lower())
        if canonical is None or canonical.lower() in selected_lower:
            continue
        if canonical in result:
            continue
        result.append(canonical)
        if len(result) >= max_files:
            break
    return tuple(result)


def critic_user_prompt(current_llm_input: str, draft: str) -> str:
    return current_llm_input + "\n\n--- DRAFT AUDIT TO VERIFY AND REWRITE ---\n" + draft.strip()
