import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from local_llm_code_auditor.cli import main
from local_llm_code_auditor.ollama import OllamaError, OllamaResult


def setup_repository(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "sample-app"
    repo.mkdir()
    for name in ("Program.cs", "Service.cs"):
        (repo / name).write_text("// Synthetic source\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    config = tmp_path / "audit.toml"
    config.write_text(
        '[agent]\nreport_dir="reports"\n[source_review]\nmax_files=1\n', encoding="utf-8"
    )
    return repo, config


def response(text: str, reason: str = "stop") -> OllamaResult:
    return OllamaResult(text, True, reason, 100, 20, None, None)


def report(tmp_path: Path) -> str:
    return next((tmp_path / "reports" / "sample-app").glob("*.md")).read_text(encoding="utf-8")


def test_static_cli_never_runs_repository_build_by_default(tmp_path):
    repo, config = setup_repository(tmp_path)
    with patch("sys.argv", ["auditor", "--config", str(config), "--repo", str(repo), "--no-llm"]):
        with patch("local_llm_code_auditor.cli.dotnet_audit") as build:
            assert main() == 0
            build.assert_not_called()
    text = report(tmp_path)
    assert "Project context status: **DISABLED**" in text
    assert "Audit LLM response: **SKIPPED**" in text


def test_cli_runs_selector_audit_and_critic_with_constrained_followup(tmp_path):
    repo, config = setup_repository(tmp_path)
    replies = [
        response('["Service.cs", "../outside.cs"]'),
        response("## Verdict\nWARNING\n## Findings\nDraft finding"),
        response("## Verdict\nGO\n## Findings\nNo supported defect.\n## Suggested actions\nNone."),
    ]
    with patch("sys.argv", ["auditor", "--config", str(config), "--repo", str(repo)]):
        with patch("local_llm_code_auditor.cli.chat", side_effect=replies) as model:
            assert main() == 0
            assert model.call_count == 3
    text = report(tmp_path)
    assert "Source follow-up files: `Service.cs`" in text
    assert "Final report source: **CRITIC**" in text
    assert "Critic pass: **COMPLETE**" in text
    assert "Draft finding" not in text
    assert "../outside.cs" not in text


def test_partial_critic_preserves_draft_and_records_fallback(tmp_path):
    repo, config = setup_repository(tmp_path)
    replies = [
        response("[]"),
        response("## Verdict\nWARNING\nRetained draft"),
        response("Incomplete critic", "length"),
    ]
    with patch("sys.argv", ["auditor", "--config", str(config), "--repo", str(repo)]):
        with patch("local_llm_code_auditor.cli.chat", side_effect=replies):
            assert main() == 0
    text = report(tmp_path)
    assert "Retained draft" in text
    assert "Incomplete critic" not in text
    assert "Critic pass: **PARTIAL_FALLBACK**" in text


def test_unavailable_model_writes_error_report_and_returns_nonzero(tmp_path):
    repo, config = setup_repository(tmp_path)
    with patch("sys.argv", ["auditor", "--config", str(config), "--repo", str(repo)]):
        with patch("local_llm_code_auditor.cli.chat", side_effect=OllamaError("Synthetic failure")):
            assert main() == 1
    assert "Audit LLM response: **ERROR**" in report(tmp_path)


def test_paired_outputs_use_same_complete_draft_and_evidence(tmp_path):
    repo, config = setup_repository(tmp_path)
    draft = "## Findings\n- LOW | Service.cs | proof | mistake | impact | change"
    replies = [response("[]"), response(draft), response("## Verdict\nGO")]
    with patch(
        "sys.argv", ["auditor", "--config", str(config), "--repo", str(repo), "--capture-draft"]
    ):
        with patch("local_llm_code_auditor.cli.chat", side_effect=replies) as model:
            assert main() == 0
    record = json.loads(next((tmp_path / "reports").rglob("*.json")).read_text(encoding="utf-8"))
    audit_evidence = model.call_args_list[1].args[3]
    critic_input = model.call_args_list[2].args[3]
    assert critic_input.startswith(audit_evidence)
    assert critic_input.endswith(record["draft"]) and record["draft"] == draft
    assert record["revision"] == record["analysis"] == "## Verdict\nGO"
    assert record["pipeline"]["final_source"] == "CRITIC"
    assert str(repo.parent) not in audit_evidence


def test_partial_selector_does_not_trigger_reads_and_strict_mode_exposes_failure(tmp_path):
    repo, config = setup_repository(tmp_path)
    with patch(
        "sys.argv", ["auditor", "--config", str(config), "--repo", str(repo), "--strict-pipeline"]
    ):
        with patch(
            "local_llm_code_auditor.cli.chat",
            side_effect=[
                response('["Service.cs"]', "length"),
                response("draft"),
                response("revision"),
            ],
        ):
            assert main() == 3
    record = json.loads(next((tmp_path / "reports").rglob("*.json")).read_text(encoding="utf-8"))
    assert record["pipeline"]["selector"] == "PARTIAL"
    assert record["followup_files"] == []
    assert "draft" not in record
