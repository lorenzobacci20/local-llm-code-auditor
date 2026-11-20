import json
import subprocess
from pathlib import Path

import pytest

from scripts import evaluate


@pytest.fixture(scope="module")
def deterministic_run(tmp_path_factory):
    output = tmp_path_factory.mktemp("evaluation") / "results"
    assert evaluate.main(["--output", str(output)]) == 0
    return output, json.loads((output / "manifest.json").read_text(encoding="utf-8"))


def test_real_cli_checks_six_cases_and_distinguishes_semantics_from_rules(deterministic_run):
    output, manifest = deterministic_run
    assert manifest["summary"] == {"total": 6, "complete": 6}
    assert manifest["mode"] == "deterministic"
    assert manifest["llm_quality"] == "NOT_EVALUATED"
    results = {case["case_id"]: case for case in manifest["cases"]}
    assert results["c01"]["deterministic_oracle"]["observed_rule_ids"] == [
        "ASPNET_PROD_DETAILED_ERRORS",
        "ASPNET_PROD_LOCALHOST",
        "ASPNET_PROD_VERBOSE_LOGGING",
    ]
    for case_id in ("c02", "c03", "c04", "c05", "c06"):
        # Semantic defects in c03/c05 are deliberately outside the static rule oracle.
        assert results[case_id]["deterministic_oracle"]["observed_rule_ids"] == []
    for case in results.values():
        assert case["deterministic_oracle"]["status"] == "PASS"
        assert case["pipeline"]["audit"] == "SKIPPED"
        assert case["llm_quality"] == "NOT_EVALUATED"
        assert (output / case["report"]).is_file()


def test_ground_truth_and_identifying_paths_do_not_enter_target(deterministic_run):
    output, manifest = deterministic_run
    assert (output / "ground-truth.json").is_file()
    for case in manifest["cases"]:
        repo = output / case["case_id"] / "sample-app"
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.splitlines()
        assert set(tracked) == {
            "Program.cs",
            "SampleApp.csproj",
            "Services/PricingService.cs",
            "appsettings.Production.json",
        }
        assert not list(repo.glob("*truth*"))
        assert set(case["input_files_sha256"]) == set(tracked)
        report = (output / case["report"]).read_text(encoding="utf-8")
        assert str(output) not in report
        path_line = next(
            line for line in report.splitlines() if line.startswith("- Repository path: `")
        )
        audited_path = Path(path_line.removeprefix("- Repository path: `").removesuffix("`"))
        assert audited_path.name == "sample-app"
        assert audited_path.parent.name.startswith("auditor-eval-")
        assert "Project context status: **DISABLED**" in report


def test_model_prose_cannot_change_deterministic_oracle(deterministic_run):
    output, manifest = deterministic_run
    report = (output / manifest["cases"][1]["report"]).read_text(encoding="utf-8")
    report += "\n## Findings\n- HIGH [ASPNET_PROD_LOCALHOST] Invented model claim.\n"
    _, oracle = evaluate.inspect_report(report, [])
    assert oracle["status"] == "PASS"
    assert oracle["observed_rule_ids"] == []


@pytest.mark.parametrize("failure", ["git_unavailable", "timeout", "cli_error"])
def test_execution_errors_never_count_as_complete(tmp_path, monkeypatch, failure):
    original = evaluate.run_command

    def run(command, cwd, deadline):
        if failure == "git_unavailable":
            raise FileNotFoundError("Synthetic missing Git")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 1, output=b"partial output")
        if "local_llm_code_auditor.cli" in command:
            return subprocess.CompletedProcess(command, 1, "", "Synthetic CLI failure")
        return original(command, cwd, deadline)

    monkeypatch.setattr(evaluate, "run_command", run)
    output = tmp_path / "results"
    assert evaluate.main(["--case", "c01", "--output", str(output)]) == 1
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["summary"] == {"total": 1, "complete": 0}
    case = manifest["cases"][0]
    assert case["status"] == ("TIMEOUT" if failure == "timeout" else "ERROR")
    assert case["error"] is not None
    assert case["deterministic_oracle"]["status"] == "NOT_EVALUATED"
    assert case["llm_quality"] == "NOT_EVALUATED"
    assert (output / "c01" / "stderr.log").exists()


def test_zero_exit_with_critic_fallback_is_incomplete(tmp_path, monkeypatch):
    original = evaluate.run_command

    def run(command, cwd, deadline):
        if "local_llm_code_auditor.cli" not in command:
            return original(command, cwd, deadline)
        # Exercise the real CLI offline, then simulate only model completion telemetry.
        completed = original([*command, "--no-llm"], cwd, deadline)
        assert completed.returncode == 0
        report = next((cwd / "reports" / "sample-app").glob("*.md"))
        text = report.read_text(encoding="utf-8")
        text = text.replace("Audit LLM response: **SKIPPED**", "Audit LLM response: **COMPLETE**")
        text = text.replace(
            "Source follow-up selector: **SKIPPED_NO_LLM**",
            "Source follow-up selector: **SKIPPED_NO_REMAINING_FILES**",
        )
        text = text.replace("Critic pass: **SKIPPED_NO_LLM**", "Critic pass: **PARTIAL_FALLBACK**")
        report.write_text(text, encoding="utf-8")
        return completed

    monkeypatch.setattr(evaluate, "run_command", run)
    output = tmp_path / "results"
    assert evaluate.main(["--case", "c03", "--llm", "--output", str(output)]) == 1
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    case = manifest["cases"][0]
    assert manifest["summary"]["complete"] == 0
    assert case["cli_returncode"] == 0
    assert case["status"] == "INCOMPLETE"
    assert case["deterministic_oracle"]["status"] == "PASS"
    assert case["llm_quality"] == "NOT_EVALUATED"


def test_existing_output_is_preserved(tmp_path):
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        evaluate.main(["--output", str(tmp_path)])
    assert exc.value.code == 2
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "manifest.json").exists()


def test_critic_off_requires_completed_audit_and_draft_source():
    pipeline = {
        "context": "DISABLED",
        "selector": "SKIPPED_NO_REMAINING_FILES",
        "audit": "COMPLETE",
        "critic": "DISABLED",
        "final_source": "DRAFT",
    }
    assert evaluate.pipeline_complete(pipeline, llm=True, critic="off")
    pipeline["audit"] = "ERROR"
    assert not evaluate.pipeline_complete(pipeline, llm=True, critic="off")
