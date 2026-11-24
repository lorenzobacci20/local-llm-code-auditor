import json
from unittest.mock import MagicMock, patch

import pytest

from local_llm_code_auditor.ollama import OllamaError, OllamaResult, chat


def test_thinking_toggle_is_explicit_and_omitted_for_default():
    for think in (None, False, True):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.side_effect = [
            b'{"details":{"format":"gguf"}}',
            b'{"message":{"content":"Synthetic response"},"done":true}',
        ]
        with patch("local_llm_code_auditor.ollama.request.build_opener", return_value=opener):
            result = chat(
                "http://127.0.0.1:11434", "test-model", "system", "synthetic", think=think
            )
        payload = json.loads(opener.open.call_args.args[0].data)
        if think is None:
            assert "think" not in payload
        else:
            assert payload["think"] is think
        assert result.complete


@pytest.mark.parametrize(
    "info",
    [
        {"remote_host": "https://example.invalid", "details": {"format": "gguf"}},
        {"remote_model": "example", "details": {"format": "gguf"}},
        {"details": {}},
        [],
    ],
)
def test_remote_or_unverifiable_model_gets_no_evidence(info):
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(info).encode()
    with patch("local_llm_code_auditor.ollama.request.build_opener", return_value=opener):
        with pytest.raises(OllamaError):
            chat("http://localhost", "alias", "system", "repository evidence")
    assert opener.open.call_count == 1
    query = opener.open.call_args.args[0]
    assert query.full_url.endswith("/api/show") and json.loads(query.data) == {"model": "alias"}


def test_cloud_tag_rejected_before_connection():
    with patch("local_llm_code_auditor.ollama.request.build_opener") as connect:
        with pytest.raises(OllamaError):
            chat("http://localhost", "example:cloud", "system", "repository evidence")
        connect.assert_not_called()


def test_empty_message_cannot_be_a_successful_review():
    assert not OllamaResult(" ", True, "stop", None, None, None, None).complete


def test_last_transport_boundary_masks_input_and_response():
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value.read.side_effect = [
        b'{"details":{"format":"gguf"}}',
        b'{"message":{"content":"token=fixture-only-response"},"done":true}',
    ]
    with patch("local_llm_code_auditor.ollama.request.build_opener", return_value=opener):
        result = chat("http://localhost", "example", "system", "ApiKey=fixture-only-input")
    assert b"fixture-only" not in opener.open.call_args.args[0].data
    assert result.content == "[REDACTED]"


def test_ollama_result_marks_length_as_partial():
    result = OllamaResult(
        content="x",
        done=True,
        done_reason="length",
        prompt_eval_count=100,
        eval_count=50,
        total_duration_ns=2_000_000_000,
        eval_duration_ns=1_000_000_000,
    )

    assert result.complete is False
    assert result.tokens_per_second == 50.0


def test_ollama_result_complete_without_length_stop():
    result = OllamaResult(
        content="x",
        done=True,
        done_reason="stop",
        prompt_eval_count=100,
        eval_count=10,
        total_duration_ns=None,
        eval_duration_ns=None,
    )

    assert result.complete is True
    assert result.tokens_per_second is None
