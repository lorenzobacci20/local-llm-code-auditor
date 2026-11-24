import hashlib
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


def test_real_cli_checks_dataset_and_distinguishes_semantics_from_rules(deterministic_run):
    output, manifest = deterministic_run
    assert manifest["summary"] == {"total": 22, "complete": 22}
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
        if case["case_id"] in {f"c{i:02}" for i in range(1, 7)}:
            assert set(tracked) == {
                "Program.cs",
                "SampleApp.csproj",
                "Services/PricingService.cs",
                "appsettings.Production.json",
            }
        assert all(Path(path).suffix in {".cs", ".json", ".csproj", ".py"} for path in tracked)
        assert not {"cases.json", "ground-truth.json", "judgments.json"}.intersection(tracked)
        assert not list(repo.glob("*truth*"))
        assert set(case["input_files_sha256"]) == set(tracked)
        report = (output / case["report"]).read_text(encoding="utf-8")
        assert str(output) not in report
        assert "- Repository: `sample-app`" in report
        assert "auditor-eval-" not in report
        assert "Project context status: **DISABLED**" in report


def test_selector_challenge_excludes_required_dependency_from_initial_sample(deterministic_run):
    _, manifest = deterministic_run
    for case in manifest["cases"]:
        if case["case_id"] in {"c19", "c20"}:
            assert len(case["files"]) == 3
            assert "invoice_service.py" in case["files"]
            assert "rounding.py" not in case["files"]
            assert "rounding.py" in case["input_files_sha256"]
            assert not case["selector_target_read"]


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
        sidecar = report.with_suffix(".json")
        document = json.loads(sidecar.read_text(encoding="utf-8"))
        document["markdown_sha256"] = hashlib.sha256(report.read_bytes()).hexdigest()
        document["pipeline"].update(
            audit="COMPLETE", selector="SKIPPED_NO_REMAINING_FILES", critic="PARTIAL_FALLBACK"
        )
        sidecar.write_text(json.dumps(document), encoding="utf-8")
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


def test_verified_judgments_are_bound_to_actual_outputs_and_seeds(tmp_path):
    from scripts.score_evaluation import score

    def write(name, obj):
        (tmp_path / name).write_text(json.dumps(obj), encoding="utf-8")

    draft, revision = "Off by one at ten. Other issue.", "Off by one at ten."
    cases = [{"case_id": "sample", "status": "COMPLETE", "structured_report": "report.json"}]
    write("report.json", {"draft": draft, "revision": revision})
    write("ground-truth.json", {"cases": [{"id": "sample", "defects": [{"id": "sample.1"}]}]})
    truth_hash = hashlib.sha256((tmp_path / "ground-truth.json").read_bytes()).hexdigest()
    cases[0]["pair"] = {
        "draft_sha256": hashlib.sha256(draft.encode()).hexdigest(),
        "revision_sha256": hashlib.sha256(revision.encode()).hexdigest(),
    }
    write(
        "manifest.json",
        {
            "settings": {"paired": True},
            "dataset_sha256": "h",
            "ground_truth_sha256": truth_hash,
            "cases": cases,
        },
    )
    seeded = {
        "classification": "seeded",
        "defect_id": "sample.1",
        "reason": "Fixture contract",
        "quote": "Off by one at ten.",
    }
    extra = {
        "classification": "unsupported",
        "reason": "Contradicted by the guard",
        "quote": "Other issue.",
    }
    reviews = []
    for stage, response in [("draft", draft), ("revision", revision)]:
        reviews.append(
            {
                "case_id": "sample",
                "stage": stage,
                "artifact_sha256": hashlib.sha256(response.encode()).hexdigest(),
                "status": "verified",
                "reviewer": "fixture",
                "findings": [seeded],
                "missed_defects": [],
            }
        )
    reviews[0]["findings"].append(extra)
    record = {"dataset_sha256": "h", "reviews": reviews}
    write("judgments.json", record)
    result = score(tmp_path)["stages"]
    assert result["draft"]["precision"] == 0.5
    assert (
        result["revision"]["precision"]
        == result["revision"]["recall"]
        == result["revision"]["f1"]
        == 1
    )
    reviews[0]["status"] = "pending"
    write("judgments.json", record)
    with pytest.raises(ValueError, match="human adjudication"):
        score(tmp_path)
    reviews[0]["status"] = "verified"
    reviews[0]["missed_defects"] = ["sample.1"]
    write("judgments.json", record)
    with pytest.raises(ValueError, match="remaining seeded"):
        score(tmp_path)
    write("report.json", {"draft": "another independent run", "revision": revision})
    with pytest.raises(ValueError, match="artifact"):
        score(tmp_path)
    reviews[0]["artifact_sha256"] = hashlib.sha256(b"another independent run").hexdigest()
    write("judgments.json", record)
    with pytest.raises(ValueError, match="artifact"):
        score(tmp_path)
    write("ground-truth.json", {"cases": []})
    with pytest.raises(ValueError, match="Ground truth"):
        score(tmp_path)


def test_paired_mode_requires_local_model_and_enabled_critic(tmp_path):
    with pytest.raises(SystemExit):
        evaluate.main(["--paired", "--output", str(tmp_path / "a")])
    with pytest.raises(SystemExit):
        evaluate.main(["--llm", "--paired", "--critic", "off", "--output", str(tmp_path / "b")])
    assert list(tmp_path.iterdir()) == []


def test_suite_budget_marks_remaining_cases_without_starting_them(monkeypatch, tmp_path):
    from types import SimpleNamespace

    now = [0.0]
    monkeypatch.setattr(evaluate, "time", SimpleNamespace(monotonic=lambda: now[0]))

    def one_case(case, destination, args, deadline):
        assert case["id"] == "c01"
        now[0] = deadline
        return {"case_id": case["id"], "status": "COMPLETE", "report": None}

    monkeypatch.setattr(evaluate, "run_case", one_case)
    destination = tmp_path / "run"
    assert (
        evaluate.main(
            ["--case", "c01", "--case", "c02", "--suite-timeout", "1", "--output", str(destination)]
        )
        == 1
    )
    manifest = json.loads((destination / "manifest.json").read_text())
    assert [case["status"] for case in manifest["cases"]] == ["COMPLETE", "NOT_STARTED"]
    assert manifest["cases"][1]["error"]["type"] == "SUITE_TIMEOUT"
    assert not (destination / "c02").exists()
