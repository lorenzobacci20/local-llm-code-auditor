import subprocess
from unittest.mock import patch

import pytest

from local_llm_code_auditor.context import load_context
from local_llm_code_auditor.git import RepositoryPathError, snapshot
from local_llm_code_auditor.privacy import redact
from local_llm_code_auditor.process import CommandResult
from local_llm_code_auditor.source_review import collect, extend_with_followup


@pytest.mark.parametrize(
    "line",
    [
        'const string apiKey = "fixture-value";',
        '"Secret": "fixture-value"',
        "Server=example;Pwd=fixture-value",
        "Authorization: Bearer fixture-value",
        "use https://account:fixture-value@example.invalid/path",
        "access_token=\nfixture-value",
        "client_secret: |\n  fixture-value\n  second-fixture-value",
    ],
)
def test_mask_common_secret_shapes_preserves_neighbouring_evidence(line):
    text = "before\n" + line + "\nafter\n"
    masked = redact(text)
    assert masked.startswith("before\n") and masked.endswith("\nafter\n")
    assert "fixture-value" not in masked
    assert masked.count("\n") == text.count("\n")
    assert redact(masked) == masked


def test_diff_prefixed_multiline_private_key_body_is_masked():
    marker = "PRIVATE" + " KEY"
    diff = f"+-----BEGIN {marker}-----\n+fixture-material\n+-----END {marker}-----\n+safe"
    assert redact(diff).splitlines() == ["[REDACTED]"] * 3 + ["+safe"]


def test_diff_and_commit_message_are_sanitized_before_prompt(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init")
    file = tmp_path / "Service.py"
    file.write_text("valid = True\n", encoding="utf-8")
    git("add", ".")
    git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "synthetic ApiKey=fixture-value",
    )
    file.write_text("client_secret = 'fixture-value'\n", encoding="utf-8")
    result = snapshot(tmp_path, 4096)
    assert "fixture-value" not in result.diff + result.recent_log
    assert "[REDACTED]" in result.diff and "[REDACTED]" in result.recent_log


def test_failed_status_is_a_collection_error(tmp_path):
    bad = CommandResult(["git", "status"], 124, "", "fixture timeout")
    with patch("local_llm_code_auditor.git.resolve_repository", return_value=tmp_path):
        with patch("local_llm_code_auditor.git.run", return_value=bad):
            with pytest.raises(RepositoryPathError, match="status failed"):
                snapshot(tmp_path, 1000)


def test_context_and_followup_mask_before_truncation(tmp_path):
    (tmp_path / "AGENTS.md").write_text(
        "client_secret: fixture-value\ncontext details", encoding="utf-8"
    )
    bundle = load_context(tmp_path, "app", 100)
    assert "[REDACTED]" in bundle.text and "fixture" not in bundle.text
    (tmp_path / "Service.py").write_text("api_key = 'fixture-value'\n", encoding="utf-8")
    with patch("local_llm_code_auditor.source_review._git_paths", return_value=("Service.py",)):
        review = collect(tmp_path, max_files=0)
    extra = extend_with_followup(
        tmp_path,
        review,
        ("Service.py",),
        total_max_chars=500,
        max_file_chars=15,
    )
    assert extra.redacted_lines == 1
    assert "[REDACTED]" in extra.text and "fixture" not in extra.text
