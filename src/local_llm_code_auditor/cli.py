from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .aspnet import audit as aspnet_audit
from .config import load_config
from .context import compose_llm_input, discover_context_root, load_context
from .dotnet import DotnetAudit
from .dotnet import audit as dotnet_audit
from .efcore import audit as efcore_audit
from .git import RepositoryPathError, discover_repositories, resolve_repository, snapshot
from .llm_review import (
    CRITIC_SYSTEM_PROMPT,
    FOLLOWUP_SYSTEM_PROMPT,
    critic_user_prompt,
    followup_user_prompt,
    parse_followup_files,
    remaining_inventory,
)
from .ollama import OllamaError, OllamaResult, chat, validate_local_url
from .report import SYSTEM_PROMPT, ReportMetadata, prompt_for, render_repo_section, write_report
from .source_review import (
    adaptive_source_budget,
    extend_with_followup,
)
from .source_review import (
    collect as collect_source_review,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nightly local LLM code audit agent")
    parser.add_argument("--config", type=Path, default=Path("agent.toml"))
    parser.add_argument(
        "--repo", action="append", type=Path, help="Audit only this repository (repeatable)"
    )
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument(
        "--run-build", action="store_true", help="Run .NET builds/tests (trusted repositories only)"
    )
    execution.add_argument(
        "--skip-build", action="store_true", help="Explicitly keep the default static-only mode"
    )
    parser.add_argument("--no-llm", action="store_true", help="Collect deterministic evidence only")
    parser.add_argument("--model", help="Override the configured Ollama model for this run")
    parser.add_argument(
        "--num-ctx", type=int, help="Override requested Ollama context for this run"
    )
    parser.add_argument(
        "--num-predict", type=int, help="Override maximum generated tokens for this run"
    )
    return parser


def _positive_override(name: str, value: int | None, default: int) -> int:
    if value is None:
        return default
    if value <= 0:
        raise ValueError(f"{name} must be > 0")
    return value


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = load_config(args.config)
        validate_local_url(config.ollama_url)
        model = args.model or config.model
        num_ctx = _positive_override("--num-ctx", args.num_ctx, config.num_ctx)
        num_predict = _positive_override("--num-predict", args.num_predict, config.num_predict)
    except (OSError, ValueError, TypeError, OllamaError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    context_root = None
    if config.context_enabled:
        context_root = discover_context_root(config.context_path, config.roots, args.config)
        if context_root is not None:
            print(f"Project context: {context_root}")
        else:
            print("Project context not found; continuing without durable context.", file=sys.stderr)

    try:
        if args.repo:
            repos = list(dict.fromkeys(resolve_repository(path) for path in args.repo))
        else:
            repos = discover_repositories(
                config.roots, exclude_dir_globs=config.discovery_exclude_dirs
            )
    except RepositoryPathError as exc:
        print(f"Invalid --repo: {exc}", file=sys.stderr)
        return 2

    if not repos:
        print("No Git repositories found.", file=sys.stderr)
        return 2

    overall_exit = 0
    for repo in repos:
        print(f"Auditing {repo}...")
        try:
            snap = snapshot(repo, config.max_diff_chars, config.include_untracked_names)
        except RepositoryPathError as exc:
            print(f"Cannot audit {repo}: {exc}", file=sys.stderr)
            overall_exit = 2
            continue

        dotnet_result = (
            dotnet_audit(repo, config.command_timeout_seconds)
            if args.run_build
            else DotnetAudit(detected=False)
        )
        aspnet_result = aspnet_audit(repo)
        efcore_result = efcore_audit(repo, snap.status)

        deterministic_high = any(
            finding.severity == "HIGH"
            for finding in (*aspnet_result.findings, *efcore_result.findings)
        )
        if (
            (dotnet_result.build is not None and not dotnet_result.build.ok)
            or dotnet_result.test_status == "FAILED"
            or deterministic_high
        ):
            overall_exit = max(overall_exit, 1)

        durable_context = (
            load_context(context_root, repo.name, config.context_max_chars)
            if config.context_enabled
            else load_context(None, repo.name, config.context_max_chars)
        )
        if not config.context_enabled:
            durable_context.status = "DISABLED"

        base_evidence = prompt_for(
            snap,
            dotnet_result,
            config.max_command_output_chars,
            aspnet=aspnet_result,
            efcore=efcore_result,
            source_review=None,
        )
        base_llm_input = compose_llm_input(durable_context, base_evidence.text)
        source_budget = adaptive_source_budget(
            num_ctx=num_ctx,
            num_predict=num_predict,
            base_prompt_chars=len(base_llm_input),
            configured_max_chars=config.source_review_max_chars,
        )

        followup_possible = (
            config.source_review_enabled
            and config.source_review_followup_enabled
            and not args.no_llm
            and config.source_review_followup_max_files > 0
        )
        initial_source_budget = source_budget
        if followup_possible and source_budget > 0:
            initial_source_budget = max(1, (source_budget * 2) // 3)

        source_review_result = collect_source_review(
            repo,
            enabled=config.source_review_enabled,
            max_chars=initial_source_budget,
            max_files=config.source_review_max_files,
            max_file_chars=config.source_review_max_file_chars,
            exclude_dir_globs=config.discovery_exclude_dirs,
        )
        source_review_result.budget_chars = source_budget

        initial_evidence = prompt_for(
            snap,
            dotnet_result,
            config.max_command_output_chars,
            aspnet=aspnet_result,
            efcore=efcore_result,
            source_review=source_review_result,
        )
        initial_llm_input = compose_llm_input(durable_context, initial_evidence.text)

        selector_result: OllamaResult | None = None
        selector_status = "SKIPPED"
        if followup_possible and remaining_inventory(source_review_result):
            remaining_chars = max(0, source_budget - len(source_review_result.text))
            followup_chars = min(config.source_review_followup_max_chars, remaining_chars)
            if followup_chars > 0:
                try:
                    selector_result = chat(
                        config.ollama_url,
                        model,
                        FOLLOWUP_SYSTEM_PROMPT,
                        followup_user_prompt(
                            initial_llm_input,
                            source_review_result,
                            config.source_review_followup_max_files,
                        ),
                        num_ctx=num_ctx,
                        num_predict=min(1_024, num_predict),
                        timeout=config.llm_timeout_seconds,
                        think=config.think,
                    )
                    selector_status = "COMPLETE" if selector_result.complete else "PARTIAL"
                    requested = parse_followup_files(
                        selector_result.content,
                        allowed_files=remaining_inventory(source_review_result),
                        already_selected=source_review_result.files,
                        max_files=config.source_review_followup_max_files,
                    )
                    if selector_result.complete and not requested:
                        selector_status = "COMPLETE_NO_FILES"

                    source_review_result = extend_with_followup(
                        repo,
                        source_review_result,
                        requested,
                        total_max_chars=min(
                            source_budget,
                            len(source_review_result.text) + followup_chars,
                        ),
                        max_file_chars=config.source_review_max_file_chars,
                    )
                    source_review_result.budget_chars = source_budget
                except OllamaError as exc:
                    selector_status = "ERROR_FALLBACK"
                    print(f"Follow-up source selector failed for {repo}: {exc}", file=sys.stderr)
        elif followup_possible:
            selector_status = "SKIPPED_NO_REMAINING_FILES"
        elif config.source_review_followup_enabled and args.no_llm:
            selector_status = "SKIPPED_NO_LLM"
        elif not config.source_review_followup_enabled:
            selector_status = "DISABLED"

        evidence = prompt_for(
            snap,
            dotnet_result,
            config.max_command_output_chars,
            aspnet=aspnet_result,
            efcore=efcore_result,
            source_review=source_review_result,
        )
        llm_input = compose_llm_input(durable_context, evidence.text)

        ollama_result: OllamaResult | None = None
        critic_result: OllamaResult | None = None
        critic_status = "SKIPPED"
        final_report_source = "DRAFT"

        if args.no_llm:
            analysis = (
                "## Verdict\nWARNING\n\n"
                "## Findings\n"
                "- INFO: LLM analysis skipped. Deterministic and bounded source evidence were collected only.\n\n"
                "## Suggested actions\n"
                "Inspect deterministic analyzer findings, selected source evidence, and build/test evidence manually."
            )
            llm_status = "SKIPPED"
            critic_status = "SKIPPED_NO_LLM"
        else:
            try:
                ollama_result = chat(
                    config.ollama_url,
                    model,
                    SYSTEM_PROMPT,
                    llm_input,
                    num_ctx=num_ctx,
                    num_predict=num_predict,
                    timeout=config.llm_timeout_seconds,
                    think=config.think,
                )
                draft = ollama_result.content
                analysis = draft
                llm_status = "COMPLETE" if ollama_result.complete else "PARTIAL"
                if not ollama_result.complete:
                    overall_exit = max(overall_exit, 1)

                if config.source_review_critic_enabled and ollama_result.complete:
                    try:
                        critic_result = chat(
                            config.ollama_url,
                            model,
                            CRITIC_SYSTEM_PROMPT,
                            critic_user_prompt(llm_input, draft),
                            num_ctx=num_ctx,
                            num_predict=num_predict,
                            timeout=config.llm_timeout_seconds,
                            think=config.think,
                        )
                        if critic_result.complete:
                            analysis = critic_result.content
                            critic_status = "COMPLETE"
                            final_report_source = "CRITIC"
                        else:
                            critic_status = "PARTIAL_FALLBACK"
                    except OllamaError as exc:
                        critic_status = "ERROR_FALLBACK"
                        print(f"Audit critic failed for {repo}: {exc}", file=sys.stderr)
                elif not config.source_review_critic_enabled:
                    critic_status = "DISABLED"
                else:
                    critic_status = "SKIPPED_AUDIT_PARTIAL"
            except OllamaError as exc:
                analysis = (
                    "## Verdict\nWARNING\n\n"
                    "## Findings\n"
                    f"- HIGH: Ollama analysis failed: `{exc}`\n\n"
                    "## Suggested actions\n"
                    f"Verify Ollama is running and model `{model}` is installed."
                )
                llm_status = "ERROR"
                critic_status = "SKIPPED_AUDIT_ERROR"
                overall_exit = max(overall_exit, 1)

        metadata = ReportMetadata(
            repo_path=str(snap.path),
            branch=snap.branch,
            head=snap.head,
            model=model,
            num_ctx=num_ctx,
            num_predict=num_predict,
            evidence=evidence,
            llm_status=llm_status,
            aspnet=aspnet_result,
            efcore=efcore_result,
            source_review=source_review_result,
            context_status=durable_context.status,
            context_root=str(durable_context.root) if durable_context.root is not None else None,
            context_files=durable_context.files,
            context_chars=durable_context.total_chars,
            context_truncated=durable_context.truncated,
            prompt_chars=len(llm_input),
            ollama=ollama_result,
            selector_status=selector_status,
            selector_ollama=selector_result,
            critic_status=critic_status,
            critic_ollama=critic_result,
            final_report_source=final_report_source,
        )
        section = render_repo_section(repo.name, analysis)
        report_path = write_report(config.report_dir, repo.name, section, metadata=metadata)
        print(f"Report written to {report_path}")

    return overall_exit


if __name__ == "__main__":
    raise SystemExit(main())
