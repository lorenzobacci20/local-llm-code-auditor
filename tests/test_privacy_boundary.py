from unittest.mock import patch
from urllib import request

import pytest

from local_llm_code_auditor.cli import main
from local_llm_code_auditor.context import load_context
from local_llm_code_auditor.ollama import OllamaError, _NoRedirect, chat, validate_local_url
from local_llm_code_auditor.source_review import collect, extend_with_followup


@pytest.mark.parametrize(
    "url",
    [
        "https://example.test",
        "http://192.0.2.1:11434",
        "file:///tmp/data",
        "http://127.0.0.1@evil.test",
        "http://user:pass@localhost:11434",
        "http://localhost:11434/forward",
        "http://localhost/?target=external",
    ],
)
def test_remote_or_ambiguous_endpoints_are_rejected_before_network(url):
    with patch("local_llm_code_auditor.ollama.request.build_opener") as opener:
        with pytest.raises(OllamaError):
            chat(url, "test-model", "system", "synthetic evidence")
        opener.assert_not_called()


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"]
)
def test_loopback_endpoints_are_accepted(url):
    assert validate_local_url(url) == url


def test_redirect_cannot_forward_repository_evidence():
    with pytest.raises(OllamaError, match="redirects are disabled"):
        _NoRedirect().redirect_request(
            request.Request("http://localhost:11434/api/chat"),
            None,
            307,
            "redirect",
            {},
            "https://example.test/collect",
        )


def test_source_and_followup_do_not_read_symlink_outside_repository(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("DO_NOT_READ_EXTERNAL_CONTENT", encoding="utf-8")
    link = repo / "Service.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires OS privileges")
    with patch("local_llm_code_auditor.source_review._git_paths", return_value=("Service.py",)):
        review = collect(repo)
    assert review.files == ()
    assert "DO_NOT_READ_EXTERNAL_CONTENT" not in review.text
    review.candidate_files = ("Service.py",)
    followup = extend_with_followup(
        repo, review, ("Service.py",), total_max_chars=2000, max_file_chars=1000
    )
    assert followup.followup_files == ()


def test_context_does_not_follow_symlink_to_private_file(tmp_path):
    root = tmp_path / "context"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("DO_NOT_READ_EXTERNAL_CONTEXT", encoding="utf-8")
    try:
        (root / "AGENTS.md").symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires OS privileges")
    bundle = load_context(root, "sample-app", 1000)
    assert "DO_NOT_READ_EXTERNAL_CONTEXT" not in bundle.text


def test_invalid_config_returns_cli_error_without_traceback(tmp_path, capsys):
    with patch("sys.argv", ["auditor", "--config", str(tmp_path / "absent.toml")]):
        assert main() == 2
    assert "Traceback" not in capsys.readouterr().err


def test_build_execution_requires_explicit_opt_in(tmp_path):
    from local_llm_code_auditor.cli import build_parser

    assert build_parser().parse_args([]).run_build is False
    assert build_parser().parse_args(["--run-build"]).run_build is True


def test_context_paths_are_relative_to_configuration_not_current_directory(tmp_path):
    from local_llm_code_auditor.config import load_config

    config = tmp_path / "audit.toml"
    config.write_text('[agent]\nroots=["repos"]\nreport_dir="output"\n', encoding="utf-8")
    result = load_config(config)
    assert result.roots == [tmp_path / "repos"]
    assert result.report_dir == tmp_path / "output"
