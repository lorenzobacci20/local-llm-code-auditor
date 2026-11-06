from datetime import datetime, timedelta, timezone

from local_llm_code_auditor.report import EvidenceBundle, ReportMetadata, write_report


def _metadata() -> ReportMetadata:
    evidence = EvidenceBundle(
        text="evidence",
        total_chars=8,
        diff_chars_original=12,
        diff_truncated=False,
        build_output_chars_original=34,
        build_output_truncated=False,
        test_output_chars_original=56,
        test_output_truncated=True,
        test_projects=("tests/SampleApp.Tests.csproj",),
        test_status="COMPLETED",
    )
    return ReportMetadata(
        repo_path=r"C:\Projects\SampleApp",
        branch="master",
        head="abc123def456",
        model="qwen3.5:9b",
        num_ctx=65_536,
        num_predict=8_192,
        evidence=evidence,
        llm_status="COMPLETE",
        context_status="LOADED",
        context_root=r"C:\Projects\project-context",
        context_files=("AGENTS.md", "projects/sample-app/current-state.md"),
        context_chars=1234,
        context_truncated=False,
        prompt_chars=4321,
    )


def test_write_report_groups_history_by_repository_and_has_completion_marker(tmp_path):
    now = datetime(2026, 9, 2, 17, 5, 6, tzinfo=timezone(timedelta(hours=2)))

    path = write_report(
        tmp_path,
        "SampleApp",
        "## Repository: SampleApp\n\n## Verdict\nGO\n",
        metadata=_metadata(),
        now=now,
    )

    assert path == tmp_path / "SampleApp" / "2026-09-02_170506.md"
    content = path.read_text(encoding="utf-8")
    assert "# Local LLM Code Auditor Report — SampleApp" in content
    assert "Context requested: **65536 tokens**" in content
    assert "Project context status: **LOADED**" in content
    assert "Project context characters: **1234**" in content
    assert "Total user-prompt characters sent to audit LLM: **4321**" in content
    assert "Audit LLM response: **COMPLETE**" in content
    assert ".NET test projects detected: **1**" in content
    assert "`tests/SampleApp.Tests.csproj`" in content
    assert ".NET test execution status: **COMPLETED**" in content
    assert "Test output truncated: **YES**" in content
    assert "## Verdict\nGO" in content
    assert content.endswith("Local LLM Code Auditor report completed successfully.\n")


def test_write_report_sanitizes_project_folder_name(tmp_path):
    path = write_report(
        tmp_path,
        "repo:with*unsafe?chars",
        "content",
        now=datetime(2026, 9, 2, 17, 5, 6),
    )

    assert path.parent.name == "repo_with_unsafe_chars"
