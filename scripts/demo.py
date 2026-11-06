"""Audit an isolated synthetic Git repository; no model is needed by default."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run_demo(
    workspace: Path, *, llm: bool = False, model: str = "qwen3.5:9b", think: bool | None = False
) -> int:
    fixture = Path(__file__).resolve().parents[1] / "examples" / "synthetic-repo"
    repo = workspace / "sample-app"
    shutil.copytree(fixture, repo)
    for args in (
        ["init", "--initial-branch=main"],
        ["-c", "core.hooksPath=", "add", "."],
        [
            "-c",
            "user.name=Synthetic Demo",
            "-c",
            "user.email=demo@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=",
            "commit",
            "-m",
            "Synthetic fixture",
        ],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    config = workspace / "audit.toml"
    thinking_config = "" if think is None else f"think={str(think).lower()}\n"
    config.write_text(
        '[agent]\nreport_dir="reports"\nnum_ctx=16384\nnum_predict=4096\nllm_timeout_seconds=300\n'
        + thinking_config
        + "[context]\nenabled=false\n[source_review]\nmax_files=1\n",
        encoding="utf-8",
    )
    args = [
        sys.executable,
        "-m",
        "local_llm_code_auditor.cli",
        "--config",
        str(config),
        "--repo",
        str(repo),
        "--skip-build",
        "--model",
        model,
    ]
    if not llm:
        args.append("--no-llm")
    result = subprocess.run(args, capture_output=True, text=True)
    reports = sorted((workspace / "reports" / "sample-app").glob("*.md"))
    if not reports:
        print(result.stdout + result.stderr, file=sys.stderr)
        return 1
    text = reports[-1].read_text(encoding="utf-8")
    required = [
        "ASPNET_PROD_DETAILED_ERRORS",
        "ASPNET_PROD_LOCALHOST",
        "ASPNET_PROD_VERBOSE_LOGGING",
    ]
    if llm:
        required.extend(["Audit LLM response: **COMPLETE**", "Critic pass: **COMPLETE**"])
    else:
        required.extend(["Audit LLM response: **SKIPPED**", "Project context status: **DISABLED**"])
    print(text)
    if result.returncode not in (0, 1) or any(marker not in text for marker in required):
        print(result.stderr, file=sys.stderr)
        return 1
    print("Synthetic demo checks passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm", action="store_true", help="Use a real local Ollama model")
    parser.add_argument("--model", default="qwen3.5:9b")
    parser.add_argument(
        "--thinking",
        choices=["auto", "on", "off"],
        default="off",
        help="Ollama thinking mode; use auto for models without the toggle",
    )
    parser.add_argument("--output", type=Path, help="Keep the workspace in a new directory")
    args = parser.parse_args()
    think = None if args.thinking == "auto" else args.thinking == "on"
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        return run_demo(args.output.resolve(), llm=args.llm, model=args.model, think=think)
    with tempfile.TemporaryDirectory(prefix="code-auditor-demo-") as directory:
        return run_demo(Path(directory), llm=args.llm, model=args.model, think=think)


if __name__ == "__main__":
    raise SystemExit(main())
