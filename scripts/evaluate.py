"""Run six synthetic cases; score deterministic rules, leave LLM quality for human review."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from local_llm_code_auditor import __version__

DATASET = Path(__file__).resolve().parents[1] / "examples" / "evaluation"
TELEMETRY = {
    "context": "Project context status",
    "selector": "Source follow-up selector",
    "audit": "Audit LLM response",
    "critic": "Critic pass",
    "final_source": "Final report source",
}


def positive_int(value: str) -> int:
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return result


def run_command(command: list[str], cwd: Path, deadline: float) -> subprocess.CompletedProcess:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(command, 0)
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=remaining)


def inspect_report(report: str, expected_rules: list[str]) -> tuple[dict, dict]:
    # Only tool-rendered sections count. Model prose after Repository is never scored.
    header, repository_marker, _ = report.partition("\n## Repository:")
    metadata, findings_marker, findings = header.partition("\n## Deterministic analyzer findings\n")
    if not repository_marker or not findings_marker:
        raise ValueError("Report is missing its deterministic or repository section")
    if "### ASP.NET\n" not in findings or "### EF Core\n" not in findings:
        raise ValueError("Report is missing deterministic analyzer sections")
    pipeline = {}
    for key, label in TELEMETRY.items():
        match = re.search(rf"^- {re.escape(label)}: \*\*([^*]+)\*\*$", metadata, re.MULTILINE)
        if match is None:
            raise ValueError(f"Report is missing telemetry: {label}")
        pipeline[key] = match.group(1)
    observed = sorted(
        re.findall(r"^- (?:HIGH|MEDIUM|LOW|INFO) \[([A-Z0-9_]+)\]", findings, re.MULTILINE)
    )
    expected = sorted(expected_rules)
    oracle = {
        "status": "PASS" if observed == expected else "MISMATCH",
        "expected_rule_ids": expected,
        "observed_rule_ids": observed,
        "missing_rule_ids": sorted(set(expected) - set(observed)),
        "unexpected_rule_ids": sorted(set(observed) - set(expected)),
    }
    return pipeline, oracle


def pipeline_complete(pipeline: dict, *, llm: bool, critic: str) -> bool:
    if pipeline["context"] != "DISABLED":
        return False
    if not llm:
        return (
            pipeline["audit"] == "SKIPPED"
            and pipeline["selector"] == "SKIPPED_NO_LLM"
            and pipeline["critic"] == "SKIPPED_NO_LLM"
        )
    return (
        pipeline["audit"] == "COMPLETE"
        and pipeline["selector"] in {"COMPLETE", "COMPLETE_NO_FILES", "SKIPPED_NO_REMAINING_FILES"}
        and pipeline["critic"] == ("COMPLETE" if critic == "on" else "DISABLED")
        and pipeline["final_source"] == ("CRITIC" if critic == "on" else "DRAFT")
    )


def configuration(args: argparse.Namespace) -> str:
    thinking = "" if args.thinking == "auto" else f"think={str(args.thinking == 'on').lower()}\n"
    return (
        '[agent]\nreport_dir="reports"\n'
        f"model={json.dumps(args.model)}\nnum_ctx={args.num_ctx}\nnum_predict={args.num_predict}\n"
        f"llm_timeout_seconds={args.timeout}\n{thinking}"
        "[context]\nenabled=false\n[source_review]\nmax_files=16\n"
        f"critic_enabled={str(args.critic == 'on').lower()}\n"
    )


def run_case(case: dict, destination: Path, args: argparse.Namespace) -> dict:
    started = time.monotonic()
    deadline = started + args.timeout
    result = {
        "case_id": case["id"],
        "status": "ERROR",
        "cli_returncode": None,
        "report": None,
        "pipeline": None,
        "deterministic_oracle": {"status": "NOT_EVALUATED"},
        "llm_quality": "NOT_EVALUATED",
        "error": None,
    }
    stdout, stderr = "", ""
    # Neither the case ID, rubric nor user-selected output path reaches model evidence.
    with tempfile.TemporaryDirectory(prefix="auditor-eval-") as temporary:
        workspace = Path(temporary)
        repo = workspace / "sample-app"
        try:
            shutil.copytree(DATASET / "common", repo)
            shutil.copytree(DATASET / "cases" / case["id"], repo, dirs_exist_ok=True)
            result["input_files_sha256"] = {
                path.relative_to(repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(repo.rglob("*"))
                if path.is_file()
            }
            for command in (
                ["git", "init", "--initial-branch=main"],
                ["git", "-c", "core.hooksPath=", "add", "."],
                [
                    "git",
                    "-c",
                    "core.hooksPath=",
                    "-c",
                    "commit.gpgsign=false",
                    "-c",
                    "user.name=Sample",
                    "-c",
                    "user.email=sample@example.invalid",
                    "commit",
                    "-m",
                    "Sample project",
                ],
            ):
                setup = run_command(command, repo, deadline)
                setup.check_returncode()
            config = workspace / "audit.toml"
            config.write_text(configuration(args), encoding="utf-8")
            command = [
                sys.executable,
                "-m",
                "local_llm_code_auditor.cli",
                "--config",
                str(config),
                "--repo",
                str(repo),
                "--skip-build",
            ]
            if not args.llm:
                command.append("--no-llm")
            completed = run_command(command, workspace, deadline)
            stdout, stderr = completed.stdout, completed.stderr
            result["cli_returncode"] = completed.returncode
            reports = list((workspace / "reports" / "sample-app").glob("*.md"))
            if len(reports) != 1:
                raise ValueError(f"Expected one report, found {len(reports)}")
            result["report"] = str(Path(case["id"]) / reports[0].relative_to(workspace))
            pipeline, oracle = inspect_report(
                reports[0].read_text(encoding="utf-8"), case["expected_rule_ids"]
            )
            result.update(pipeline=pipeline, deterministic_oracle=oracle)
            if completed.returncode != 0:
                result["error"] = {
                    "type": "CLI_ERROR",
                    "message": f"CLI exited {completed.returncode}",
                }
            elif not pipeline_complete(pipeline, llm=args.llm, critic=args.critic):
                result["status"] = "INCOMPLETE"
                result["error"] = {
                    "type": "PIPELINE_INCOMPLETE",
                    "message": "Inspect pipeline telemetry",
                }
            elif oracle["status"] != "PASS":
                result["status"] = "ORACLE_MISMATCH"
            else:
                result["status"] = "COMPLETE"
        except subprocess.TimeoutExpired as exc:
            result["status"] = "TIMEOUT"
            result["error"] = {
                "type": "TIMEOUT",
                "message": "Total case subprocess budget exhausted",
            }
            stdout, stderr = exc.stdout or "", exc.stderr or ""
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            result["error"] = {"type": type(exc).__name__, "message": str(exc)}
            if isinstance(exc, subprocess.CalledProcessError):
                stdout, stderr = exc.stdout or "", exc.stderr or ""
        finally:
            for name, contents in (("stdout.log", stdout), ("stderr.log", stderr)):
                if isinstance(contents, bytes):
                    contents = contents.decode("utf-8", errors="replace")
                (workspace / name).write_text(contents, encoding="utf-8")
            shutil.copytree(workspace, destination)
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def main(argv: list[str] | None = None) -> int:
    dataset = json.loads((DATASET / "cases.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="List case IDs without running audits")
    parser.add_argument(
        "--case", action="append", choices=[case["id"] for case in dataset["cases"]]
    )
    parser.add_argument(
        "--output", type=Path, help="Required new output directory; never overwritten"
    )
    parser.add_argument("--llm", action="store_true", help="Opt in to a real local Ollama model")
    parser.add_argument("--model", default="qwen3.5:9b")
    parser.add_argument("--thinking", choices=["auto", "on", "off"], default="off")
    parser.add_argument("--critic", choices=["on", "off"], default="on")
    parser.add_argument("--num-ctx", type=positive_int, default=16384)
    parser.add_argument("--num-predict", type=positive_int, default=4096)
    parser.add_argument(
        "--timeout", type=positive_int, default=300, help="Total subprocess seconds per case"
    )
    args = parser.parse_args(argv)
    cases = [case for case in dataset["cases"] if not args.case or case["id"] in args.case]
    if args.list:
        for case in cases:
            print(f"{case['id']}: {case['topic']}")
        return 0
    if args.output is None:
        parser.error("--output is required unless --list is used")
    output = args.output.expanduser().resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        parser.error(f"Cannot create a new output directory: {exc}")
    manifest = {
        "schema_version": 1,
        "dataset_version": dataset["version"],
        "auditor_version": __version__,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "mode": "llm" if args.llm else "deterministic",
        "settings": {
            key: getattr(args, key)
            for key in ("model", "thinking", "critic", "num_ctx", "num_predict", "timeout")
        },
        "llm_quality": "NOT_EVALUATED",
        "cases": [],
        "summary": {"total": len(cases), "complete": 0},
    }
    # Answers and review criteria stay outside every audited Git repository.
    (output / "ground-truth.json").write_text(
        json.dumps({"version": dataset["version"], "cases": cases}, indent=2) + "\n",
        encoding="utf-8",
    )
    for case in cases:
        result = run_case(case, output / case["id"], args)
        manifest["cases"].append(result)
        manifest["summary"]["complete"] += result["status"] == "COMPLETE"
        (output / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{case['id']}: {result['status']}; LLM quality NOT_EVALUATED")
    print(f"Manifest: {output / 'manifest.json'}")
    return 0 if manifest["summary"]["complete"] == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
