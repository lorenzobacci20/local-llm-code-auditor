"""Run isolated synthetic audits and retain evidence for independent human review."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import local_llm_code_auditor
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
    env = os.environ.copy()
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_COUNT="0")
    for key in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
        "GIT_CONFIG_PARAMETERS",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
    ):
        env.pop(key, None)
    env.update(GIT_AUTHOR_DATE="2000-01-01T00:00:00Z", GIT_COMMITTER_DATE="2000-01-01T00:00:00Z")
    return subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True, timeout=remaining
    )


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


def pipeline_complete(pipeline: dict, *, llm: bool, critic: str, selector: str = "on") -> bool:
    if pipeline["context"] != "DISABLED":
        return False
    if not llm:
        return (
            pipeline["audit"] == "SKIPPED"
            and pipeline["selector"] == ("DISABLED" if selector == "off" else "SKIPPED_NO_LLM")
            and pipeline["critic"] == "SKIPPED_NO_LLM"
        )
    selected = {"COMPLETE", "COMPLETE_NO_FILES", "SKIPPED_NO_REMAINING_FILES"}
    if selector == "off":
        selected = {"DISABLED"}
    return (
        pipeline["audit"] == "COMPLETE"
        and pipeline["selector"] in selected
        and pipeline["critic"] == ("COMPLETE" if critic == "on" else "DISABLED")
        and pipeline["final_source"] == ("CRITIC" if critic == "on" else "DRAFT")
    )


def configuration(args: argparse.Namespace, max_files: int = 16) -> str:
    thinking = "" if args.thinking == "auto" else f"think={str(args.thinking == 'on').lower()}\n"
    return (
        '[agent]\nreport_dir="reports"\n'
        f"model={json.dumps(args.model)}\nnum_ctx={args.num_ctx}\nnum_predict={args.num_predict}\n"
        f"llm_timeout_seconds={args.timeout}\n{thinking}"
        f"[context]\nenabled=false\n[source_review]\nmax_files={max_files}\n"
        f"followup_enabled={str(args.selector == 'on').lower()}\n"
        f"critic_enabled={str(args.critic == 'on').lower()}\n"
    )


def materialize(case: dict, repo: Path) -> None:
    """Copy only reviewed fixture sources into the neutral target."""
    layout = case["layout"]
    if layout != "standalone":
        base = DATASET / "common" if layout == "common" else DATASET / "layouts" / layout
        shutil.copytree(base, repo, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(
        DATASET / "cases" / case["id"],
        repo,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def source_hash(directory: Path, patterns: tuple[str, ...]) -> str:
    entries = {}
    for pattern in patterns:
        for path in directory.rglob(pattern):
            relative = path.relative_to(directory).as_posix()
            data = path.read_bytes().replace(b"\r\n", b"\n")
            entries[relative] = hashlib.sha256(data).hexdigest()
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


def software_version() -> dict:
    package = Path(local_llm_code_auditor.__file__).resolve().parent
    root = DATASET.parents[1]
    revision = None
    dirty = None
    if package == root / "src" / "local_llm_code_auditor" and (root / ".git").exists():
        try:
            revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                text=True,
                timeout=3,
                stderr=subprocess.DEVNULL,
            ).strip()
            dirty = bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain"],
                    cwd=root,
                    text=True,
                    timeout=3,
                    stderr=subprocess.DEVNULL,
                ).strip()
            )
        except (OSError, subprocess.SubprocessError):
            pass
    return {"commit": revision, "dirty": dirty, "package_sha256": source_hash(package, ("*.py",))}


def ollama_metadata(model: str, deadline: float, *, loaded: bool = False) -> dict:
    """Read loopback metadata without proxies, redirects, local identifiers or model pulls."""

    def get(endpoint):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {}
        connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=min(remaining, 2))
        try:
            connection.request("GET", endpoint)
            response = connection.getresponse()
            if response.status == 200:
                obj = json.loads(response.read(1_048_577))
                if isinstance(obj, dict):
                    return obj
        except (OSError, ValueError, http.client.HTTPException):
            pass
        finally:
            connection.close()
        return {}

    endpoint = "/api/ps" if loaded else "/api/tags"
    tag = model if ":" in model.rsplit("/", 1)[-1] else model + ":latest"
    models = get(endpoint).get("models") or []
    matched = next((m for m in models if isinstance(m, dict) and m.get("name") == tag), {})
    if loaded:
        return {"loaded_bytes": matched.get("size"), "vram_bytes": matched.get("size_vram")}
    return {"version": get("/api/version").get("version"), "model_digest": matched.get("digest")}


def run_case(
    case: dict, destination: Path, args: argparse.Namespace, suite_deadline: float
) -> dict:
    started = time.monotonic()
    deadline = min(started + args.timeout, suite_deadline)
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
            materialize(case, repo)
            result["input_files_sha256"] = {
                path.relative_to(repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(repo.rglob("*"))
                if path.is_file()
            }
            for command in (
                ["git", "init", "--template=", "--initial-branch=main"],
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
            config.write_text(
                configuration(args, case.get("initial_max_files", 16)), encoding="utf-8"
            )
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
            if args.paired:
                command.append("--capture-draft")
            completed = run_command(command, workspace, deadline)
            stdout, stderr = completed.stdout, completed.stderr
            result["cli_returncode"] = completed.returncode
            reports = list((workspace / "reports" / "sample-app").glob("*.md"))
            if len(reports) != 1:
                raise ValueError(f"Expected one report, found {len(reports)}")
            result["report"] = (Path(case["id"]) / reports[0].relative_to(workspace)).as_posix()
            markdown = reports[0].read_text(encoding="utf-8")
            pipeline, oracle = inspect_report(markdown, case["expected_rule_ids"])
            result.update(pipeline=pipeline, deterministic_oracle=oracle)
            sidecar = reports[0].with_suffix(".json")
            structured = json.loads(sidecar.read_text(encoding="utf-8"))
            if structured.get("schema_version") != 1:
                raise ValueError("Unsupported report schema")
            if (
                structured.get("markdown_sha256")
                != hashlib.sha256(reports[0].read_bytes()).hexdigest()
            ):
                raise ValueError("Markdown bytes differ from the sidecar digest")
            if {**structured["pipeline"], "context": structured["context_status"]} != pipeline:
                raise ValueError("Markdown and structured pipeline telemetry differ")
            static_ids = sorted(
                item["id"] for item in structured["findings"] if item["origin"] == "deterministic"
            )
            if static_ids != oracle["observed_rule_ids"]:
                raise ValueError("Markdown and structured deterministic findings differ")
            result["structured_report"] = (
                Path(case["id"]) / sidecar.relative_to(workspace)
            ).as_posix()
            result["files"] = structured["files"]
            result["followup_files"] = structured["followup_files"]
            result["stages"] = structured["stages"]
            if args.llm and isinstance(structured.get("analysis"), str):
                result["analysis_sha256"] = hashlib.sha256(
                    structured["analysis"].encode()
                ).hexdigest()
            if "selector_target" in case:
                result["selector_target_read"] = case["selector_target"] in result["followup_files"]
            if args.llm:
                result["memory_after_case"] = ollama_metadata(
                    args.model, suite_deadline, loaded=True
                )
            if args.paired:
                result["pair"] = {}
                for stage in ("draft", "revision"):
                    response = structured.get(stage)
                    if isinstance(response, str) and response.strip():
                        result["pair"][stage + "_sha256"] = hashlib.sha256(
                            response.encode()
                        ).hexdigest()
                if pipeline["critic"] == "COMPLETE" and len(result["pair"]) != 2:
                    raise ValueError("A completed paired critic requires both captured responses")
            if completed.returncode != case.get("expected_cli_exit", 0):
                result["error"] = {
                    "type": "CLI_ERROR",
                    "message": f"CLI exited {completed.returncode}",
                }
            elif not pipeline_complete(
                pipeline, llm=args.llm, critic=args.critic, selector=args.selector
            ):
                result["status"] = "INCOMPLETE"
                result["error"] = {
                    "type": "PIPELINE_INCOMPLETE",
                    "message": "Inspect pipeline telemetry",
                }
            elif oracle["status"] != "PASS":
                result["status"] = "ORACLE_MISMATCH"
            elif args.llm and not structured.get("analysis"):
                raise ValueError("Complete audit lacks an analysis")
            else:
                result["status"] = "COMPLETE"
        except subprocess.TimeoutExpired as exc:
            result["status"] = "TIMEOUT"
            result["error"] = {
                "type": "TIMEOUT",
                "message": "Total case subprocess budget exhausted",
            }
            stdout, stderr = exc.stdout or "", exc.stderr or ""
        except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
            result["error"] = {"type": type(exc).__name__, "message": str(exc)}
            if isinstance(exc, subprocess.CalledProcessError):
                stdout, stderr = exc.stdout or "", exc.stderr or ""
        finally:
            for name, contents in (("stdout.log", stdout), ("stderr.log", stderr)):
                if isinstance(contents, bytes):
                    contents = contents.decode("utf-8", errors="replace")
                (workspace / name).write_text(contents, encoding="utf-8")
            # Nested test output paths easily exceed legacy Windows MAX_PATH inside .git/objects.
            target = str(destination.resolve())
            if os.name == "nt" and not target.startswith("\\\\?\\"):
                target = (
                    "\\\\?\\UNC\\" + target[2:] if target.startswith("\\\\") else "\\\\?\\" + target
                )
            shutil.copytree(workspace, target)
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
    parser.add_argument("--selector", choices=["on", "off"], default="on")
    parser.add_argument(
        "--paired",
        action="store_true",
        help="Save and compare one draft and its own critic revision",
    )
    parser.add_argument("--num-ctx", type=positive_int, default=16384)
    parser.add_argument("--num-predict", type=positive_int, default=4096)
    parser.add_argument(
        "--timeout", type=positive_int, default=300, help="Total subprocess seconds per case"
    )
    parser.add_argument(
        "--suite-timeout",
        type=positive_int,
        default=1800,
        help="Total time budget across all selected cases",
    )
    args = parser.parse_args(argv)
    cases = [case for case in dataset["cases"] if not args.case or case["id"] in args.case]
    if args.list:
        for case in cases:
            print(f"{case['id']}: {case['topic']}")
        return 0
    if args.output is None:
        parser.error("--output is required unless --list is used")
    if args.paired and (not args.llm or args.critic != "on"):
        parser.error("--paired requires --llm and --critic on")
    output = args.output.expanduser().resolve()
    if output.is_relative_to(DATASET):
        parser.error("--output must be outside the source dataset")
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        parser.error(f"Cannot create a new output directory: {exc}")
    suite_deadline = time.monotonic() + args.suite_timeout
    manifest = {
        "schema_version": 2,
        "dataset_version": dataset["version"],
        "dataset_sha256": source_hash(DATASET, ("*.json", "*.cs", "*.csproj", "*.py")),
        "software": software_version(),
        "auditor_version": __version__,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "mode": "llm" if args.llm else "deterministic",
        "settings": {
            key: getattr(args, key)
            for key in (
                "model",
                "thinking",
                "critic",
                "selector",
                "paired",
                "num_ctx",
                "num_predict",
                "timeout",
                "suite_timeout",
            )
        },
        "ollama": ollama_metadata(args.model, suite_deadline) if args.llm else None,
        "llm_quality": "NOT_EVALUATED",
        "cases": [],
        "summary": {"total": len(cases), "complete": 0},
    }
    # Answers and review criteria stay outside every audited Git repository.
    truth_file = output / "ground-truth.json"
    truth_file.write_text(
        json.dumps({"version": dataset["version"], "cases": cases}, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest["ground_truth_sha256"] = hashlib.sha256(truth_file.read_bytes()).hexdigest()
    judgments = {"schema_version": 1, "dataset_sha256": manifest["dataset_sha256"], "reviews": []}
    for case in cases:
        if time.monotonic() >= suite_deadline:
            result = {
                "case_id": case["id"],
                "status": "NOT_STARTED",
                "cli_returncode": None,
                "report": None,
                "pipeline": None,
                "llm_quality": "NOT_EVALUATED",
                "deterministic_oracle": {"status": "NOT_EVALUATED"},
                "error": {"type": "SUITE_TIMEOUT", "message": "Suite time budget exhausted"},
            }
        else:
            result = run_case(case, output / case["id"], args, suite_deadline)
        manifest["cases"].append(result)
        manifest["summary"]["complete"] += result["status"] == "COMPLETE"
        (output / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        if args.llm and result["status"] == "COMPLETE":
            stages = ("draft", "revision") if args.paired else ("final",)
            for stage in stages:
                digest = (
                    result["pair"][stage + "_sha256"] if args.paired else result["analysis_sha256"]
                )
                judgments["reviews"].append(
                    {
                        "case_id": case["id"],
                        "stage": stage,
                        "artifact_sha256": digest,
                        "status": "pending",
                        "reviewer": None,
                        "findings": [],
                        "missed_defects": [],
                        "notes": "",
                    }
                )
        if args.llm:
            (output / "judgments.json").write_text(
                json.dumps(judgments, indent=2) + "\n", encoding="utf-8"
            )
        print(f"{case['id']}: {result['status']}; LLM quality NOT_EVALUATED")
    print(f"Manifest: {output / 'manifest.json'}")
    return 0 if manifest["summary"]["complete"] == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
