from local_llm_code_auditor.ollama import OllamaResult


def test_thinking_toggle_is_explicit_and_omitted_for_default():
    import json
    from unittest.mock import MagicMock, patch

    from local_llm_code_auditor.ollama import chat

    for think in (None, False, True):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = (
            b'{"message":{"content":"Synthetic response"},"done":true}'
        )
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
