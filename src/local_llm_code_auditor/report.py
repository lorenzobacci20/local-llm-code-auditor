from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .aspnet import AspNetAudit
from .dotnet import DotnetAudit
from .efcore import EfCoreAudit
from .git import RepoSnapshot
from .ollama import OllamaResult
from .source_review import SourceReview

_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(slots=True)
class EvidenceBundle:
    text: str
    total_chars: int
    diff_chars_original: int
    diff_truncated: bool
    build_output_chars_original: int
    build_output_truncated: bool
    test_output_chars_original: int
    test_output_truncated: bool
    test_projects: tuple[str, ...] = ()
    test_status: str = "NOT_APPLICABLE"


@dataclass(slots=True)
class ReportMetadata:
    repo_path: str
    branch: str
    head: str
    model: str
    num_ctx: int
    num_predict: int
    evidence: EvidenceBundle
    llm_status: str
    aspnet: AspNetAudit | None = None
    efcore: EfCoreAudit | None = None
    source_review: SourceReview | None = None
    context_status: str = "DISABLED"
    context_root: str | None = None
    context_files: tuple[str, ...] = ()
    context_chars: int = 0
    context_truncated: bool = False
    prompt_chars: int = 0
    ollama: OllamaResult | None = None
    selector_status: str = "SKIPPED"
    selector_ollama: OllamaResult | None = None
    critic_status: str = "SKIPPED"
    critic_ollama: OllamaResult | None = None
    final_report_source: str = "DRAFT"


def _bounded_tail(text: str, limit: int) -> tuple[str, int, bool]:
    original_chars = len(text)
    truncated = original_chars > limit
    if not truncated:
        return text, original_chars, False
    return "[earlier command output truncated]\n" + text[-limit:], original_chars, True


def _safe_project_name(name: str) -> str:
    sanitized = _INVALID_PATH_CHARS.sub("_", name).strip().rstrip(". ")
    return sanitized or "repository"


def prompt_for(
    snapshot: RepoSnapshot,
    dotnet: DotnetAudit,
    max_command_output_chars: int,
    aspnet: AspNetAudit | None = None,
    efcore: EfCoreAudit | None = None,
    source_review: SourceReview | None = None,
) -> EvidenceBundle:
    sections = [
        f"Repository: {snapshot.path.name}",
        f"Path: {snapshot.path}",
        f"Branch: {snapshot.branch}",
        f"HEAD: {snapshot.head}",
        f"Diff original chars: {snapshot.diff_chars_original}",
        f"Diff truncated: {'YES' if snapshot.diff_truncated else 'NO'}",
        "\nGit status:\n" + (snapshot.status or "clean"),
        "\nRecent commits (24h):\n" + (snapshot.recent_log or "none"),
        "\nCurrent diff:\n" + (snapshot.diff or "none"),
    ]

    build_chars = 0
    build_truncated = False
    test_chars = 0
    test_truncated = False

    if dotnet.detected:
        test_projects_text = ", ".join(dotnet.test_projects) if dotnet.test_projects else "none"
        sections.append(
            "\n.NET test discovery:\n"
            f".NET test projects detected: {len(dotnet.test_projects)}\n"
            f".NET test projects: {test_projects_text}\n"
            f".NET test execution status: {dotnet.test_status}"
        )
        if dotnet.build:
            build_text, build_chars, build_truncated = _bounded_tail(
                dotnet.build.stdout + "\n" + dotnet.build.stderr,
                max_command_output_chars,
            )
            sections.append(
                f"\n.NET build exit code: {dotnet.build.returncode}\n"
                f".NET build output original chars: {build_chars}\n"
                f".NET build output truncated: {'YES' if build_truncated else 'NO'}\n" + build_text
            )
        if dotnet.test:
            test_text, test_chars, test_truncated = _bounded_tail(
                dotnet.test.stdout + "\n" + dotnet.test.stderr,
                max_command_output_chars,
            )
            sections.append(
                f"\n.NET test exit code: {dotnet.test.returncode}\n"
                f".NET test output original chars: {test_chars}\n"
                f".NET test output truncated: {'YES' if test_truncated else 'NO'}\n" + test_text
            )
        elif dotnet.test_status == "SKIPPED_NO_TEST_PROJECTS":
            sections.append(
                "\n.NET test command was not run because deterministic project discovery found no .NET test projects."
            )

    if aspnet is not None:
        sections.append("\n" + aspnet.evidence_text())
    if efcore is not None:
        sections.append("\n" + efcore.evidence_text())
    if source_review is not None:
        sections.append("\n" + source_review.evidence_text())

    text = "\n".join(sections)
    return EvidenceBundle(
        text=text,
        total_chars=len(text),
        diff_chars_original=snapshot.diff_chars_original,
        diff_truncated=snapshot.diff_truncated,
        build_output_chars_original=build_chars,
        build_output_truncated=build_truncated,
        test_output_chars_original=test_chars,
        test_output_truncated=test_truncated,
        test_projects=dotnet.test_projects,
        test_status=dotnet.test_status,
    )


SYSTEM_PROMPT = """You are a conservative senior software engineer performing a local nightly audit.
Use only the evidence and durable context supplied. Do not invent files, checks, failures, dependency state, security coverage, or conclusions not directly supported by the prompt.
If Project context is supplied, use it as durable project guidance, previous decisions, and intended state. Current live repository/code/build/test/static-analyzer evidence overrides Project context when they conflict.
Treat deterministic ASP.NET and EF Core analyzer findings as first-class evidence. Never reveal or reconstruct secret values.
Source code review evidence is a bounded, selected subset of source files, not proof that the whole repository was read. Use it to identify concrete logic, correctness, security, error-handling, concurrency, API-contract, authorization, and material maintainability defects visible in the supplied source. Never claim unselected files were reviewed or defect-free.
Prioritize correctness, security, regressions, production configuration risk, migrations, code-level defects, and test failures.
A successful build or test run proves only that the supplied build/test command succeeded; it does not prove dependencies, security, migrations, production configuration, source correctness, or the whole repository are healthy unless explicit evidence for those checks is supplied.
Never say a dependency graph, vulnerability state, production configuration, migration state, or security posture is \"green\" unless the evidence explicitly contains the corresponding check.
EF Core static evidence describes source artifacts only. Migration files, snapshots, DbContext discovery, or zero deterministic EF findings do NOT establish which migrations are applied or pending in any database. Never state or imply \"no pending migrations\", \"database is up to date\", or equivalent unless explicit non-static database-state evidence is supplied.
Never recommend `dotnet ef database update`, automatic migration execution, SQL mutation, or any other database-mutating command. The agent is read-only with respect to databases.
Zero deterministic analyzer findings means only that the implemented deterministic rules produced no findings for the supplied repository state.
Do not report a candidate concern if the supplied evidence or your own analysis shows that it is correct, intentional, acceptable, harmless, already guarded, or \"no issue\". Omit it entirely.
Before reporting an input-validation or safety defect, inspect supplied guards, allowlists, normalization, range checks, and counter-evidence.
Do not recommend adding comments or documentation for behavior that is already clear unless missing documentation creates a concrete correctness, security, operability, or material maintenance risk.
Do not use \"ensure\", \"check\", \"consider\", or \"verify\" as generic actions unless a concrete supplied finding establishes why that action is needed.
Do not repeat healthy build/analyzer telemetry as multiple findings. Telemetry already records successful checks.
Do not claim two artifacts match, align, or are consistent unless both are present in supplied evidence or a deterministic analyzer explicitly established that relationship.
Absence of an analyzer or optional check is a coverage limitation, not a defect or release blocker by itself.
Do not raise the verdict from GO to WARNING solely because optional evidence is missing.
Every suggested action must map to a concrete retained finding supported by supplied evidence.
Machine-specific paths and usernames are not secrets by themselves. A tracked IDE/user settings file such as *.csproj.user is normally LOW repository-hygiene risk unless it exposes credentials/sensitive data or causes a demonstrated failure.
Do not recommend blocking push, merge, or deployment merely because optional checks were not performed. STOP or blocking guidance requires concrete supplied evidence of a blocker.
When evidence, source review, or Project context is truncated, mention that limitation only if it materially affects confidence in a finding.
Recommendations must be internally consistent.
Never recommend automatic push, merge, production database mutation, or deployment.
Return concise Markdown with these headings exactly:
## Verdict
## Findings
## Suggested actions
Verdict must be one of GO, WARNING, STOP.
For each retained finding include severity (HIGH/MEDIUM/LOW/INFO) and concrete evidence from the supplied material.
If no actionable defect is established, Findings may contain one concise INFO statement and Suggested actions may say no action required."""


def render_repo_section(repo_name: str, analysis: str) -> str:
    return f"## Repository: {repo_name}\n\n{analysis.strip()}\n"


def _llm_telemetry(lines: list[str], prefix: str, result: OllamaResult | None) -> None:
    if result is None:
        return
    lines.append(
        f"- {prefix} prompt tokens evaluated: **{result.prompt_eval_count if result.prompt_eval_count is not None else 'not reported'}**"
    )
    lines.append(
        f"- {prefix} output tokens generated: **{result.eval_count if result.eval_count is not None else 'not reported'}**"
    )


def render_metadata(metadata: ReportMetadata) -> str:
    ev = metadata.evidence
    context_files = ", ".join(f"`{path}`" for path in metadata.context_files) or "none"
    test_projects = ", ".join(f"`{path}`" for path in ev.test_projects) or "none"
    aspnet = metadata.aspnet
    efcore = metadata.efcore
    source_review = metadata.source_review
    source_files = (
        ", ".join(f"`{path}`" for path in source_review.files)
        if source_review and source_review.files
        else "none"
    )
    followup_files = (
        ", ".join(f"`{path}`" for path in source_review.followup_files)
        if source_review and source_review.followup_files
        else "none"
    )
    source_categories = (
        ", ".join(source_review.categories)
        if source_review and source_review.categories
        else "none"
    )

    lines = [
        "## Audit telemetry",
        "",
        f"- Repository path: `{metadata.repo_path}`",
        f"- Branch: `{metadata.branch}`",
        f"- HEAD: `{metadata.head}`",
        f"- Model: `{metadata.model}`",
        f"- Context requested: **{metadata.num_ctx} tokens**",
        f"- Max generated tokens: **{metadata.num_predict}**",
        f"- Project context status: **{metadata.context_status}**",
        f"- Project context root: `{metadata.context_root or 'not available'}`",
        f"- Project context files: {context_files}",
        f"- Project context characters: **{metadata.context_chars}**",
        f"- Project context truncated: **{'YES' if metadata.context_truncated else 'NO'}**",
        f"- Live evidence characters: **{ev.total_chars}**",
        f"- Total user-prompt characters sent to audit LLM: **{metadata.prompt_chars or ev.total_chars}**",
        f"- Diff original characters: **{ev.diff_chars_original}**",
        f"- Diff truncated: **{'YES' if ev.diff_truncated else 'NO'}**",
        f"- Build output original characters: **{ev.build_output_chars_original}**",
        f"- Build output truncated: **{'YES' if ev.build_output_truncated else 'NO'}**",
        f"- .NET test projects detected: **{len(ev.test_projects)}**",
        f"- .NET test projects: {test_projects}",
        f"- .NET test execution status: **{ev.test_status}**",
        f"- Test output original characters: **{ev.test_output_chars_original}**",
        f"- Test output truncated: **{'YES' if ev.test_output_truncated else 'NO'}**",
        f"- ASP.NET analyzer: **{'DETECTED' if aspnet and aspnet.detected else 'NOT_DETECTED'}**",
        f"- ASP.NET deterministic findings: **{len(aspnet.findings) if aspnet else 0}**",
        f"- EF Core analyzer: **{'DETECTED' if efcore and efcore.detected else 'NOT_DETECTED'}**",
        f"- EF Core migrations detected: **{len(efcore.migration_files) if efcore else 0}**",
        f"- EF Core deterministic findings: **{len(efcore.findings) if efcore else 0}**",
        f"- Source code review: **{'ENABLED' if source_review and source_review.enabled else 'DISABLED'}**",
        f"- Source candidate files after filters: **{source_review.candidate_count if source_review else 0}**",
        f"- Source budget characters: **{source_review.budget_chars if source_review else 0}**",
        f"- Source files reviewed: **{len(source_review.files) if source_review else 0}**",
        f"- Source categories reviewed: {source_categories}",
        f"- Source follow-up selector: **{metadata.selector_status}**",
        f"- Source follow-up files: {followup_files}",
        f"- Source files: {source_files}",
        f"- Source original characters: **{source_review.chars_original if source_review else 0}**",
        f"- Source evidence truncated: **{'YES' if source_review and source_review.truncated else 'NO'}**",
        f"- Sensitive source lines redacted: **{source_review.redacted_lines if source_review else 0}**",
        f"- Audit LLM response: **{metadata.llm_status}**",
        f"- Critic pass: **{metadata.critic_status}**",
        f"- Final report source: **{metadata.final_report_source}**",
    ]
    if metadata.ollama is not None:
        result = metadata.ollama
        lines.extend(
            [
                f"- Ollama done: **{'YES' if result.done else 'NO'}**",
                f"- Ollama done reason: `{result.done_reason or 'not reported'}`",
                f"- Prompt tokens evaluated: **{result.prompt_eval_count if result.prompt_eval_count is not None else 'not reported'}**",
                f"- Output tokens generated: **{result.eval_count if result.eval_count is not None else 'not reported'}**",
            ]
        )
        tps = result.tokens_per_second
        lines.append(
            f"- Generation speed: **{tps:.2f} tokens/s**"
            if tps is not None
            else "- Generation speed: **not reported**"
        )
    _llm_telemetry(lines, "Selector", metadata.selector_ollama)
    _llm_telemetry(lines, "Critic", metadata.critic_ollama)
    return "\n".join(lines) + "\n"


def render_deterministic_findings(metadata: ReportMetadata) -> str:
    lines = ["## Deterministic analyzer findings", ""]
    any_findings = False
    for name, findings in (
        ("ASP.NET", metadata.aspnet.findings if metadata.aspnet else ()),
        ("EF Core", metadata.efcore.findings if metadata.efcore else ()),
    ):
        lines.append(f"### {name}")
        if findings:
            any_findings = True
            lines.extend(f.render() for f in findings)
        else:
            lines.append("- No deterministic findings.")
        lines.append("")
    if not any_findings:
        lines.append(
            "No deterministic ASP.NET/EF Core risk findings were produced for the supplied repository state."
        )
        lines.append("")
    return "\n".join(lines)


def write_report(
    report_dir: Path,
    repo_name: str,
    section: str,
    *,
    metadata: ReportMetadata | None = None,
    now: datetime | None = None,
) -> Path:
    project_dir = report_dir / _safe_project_name(repo_name)
    project_dir.mkdir(parents=True, exist_ok=True)
    generated_at = now or datetime.now().astimezone()
    if generated_at.tzinfo is None:
        generated_at = generated_at.astimezone()
    path = project_dir / f"{generated_at:%Y-%m-%d_%H%M%S}.md"
    header = (
        f"# Local LLM Code Auditor Report — {repo_name}\n\n"
        f"Generated: {generated_at.isoformat()}\n\n"
    )
    telemetry = (render_metadata(metadata) + "\n") if metadata else ""
    deterministic = (render_deterministic_findings(metadata) + "\n") if metadata else ""
    footer = "\n---\n\nLocal LLM Code Auditor report completed successfully.\n"
    path.write_text(
        header + telemetry + deterministic + section + footer,
        encoding="utf-8",
    )
    return path
