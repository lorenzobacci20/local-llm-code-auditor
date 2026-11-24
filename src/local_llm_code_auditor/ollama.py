from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from http.client import HTTPException
from ipaddress import ip_address
from urllib import error, request
from urllib.parse import urlsplit

from .privacy import redact


class OllamaError(RuntimeError):
    pass


def validate_local_url(base_url: str) -> str:
    """Keep repository evidence on an explicit loopback HTTP(S) endpoint."""
    try:
        url = urlsplit(base_url)
        host = url.hostname
        local = host == "localhost" or (host is not None and ip_address(host).is_loopback)
        valid = (
            local
            and url.scheme in {"http", "https"}
            and url.username is None
            and url.password is None
            and url.path in {"", "/"}
            and not url.query
            and not url.fragment
        )
        _ = url.port
    except ValueError:
        valid = False
    if not valid:
        raise OllamaError(
            "Ollama URL must be an HTTP(S) loopback origin without credentials or a path"
        )
    return base_url.rstrip("/")


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise OllamaError("Ollama redirects are disabled to protect repository evidence")


@dataclass(slots=True)
class OllamaResult:
    content: str
    done: bool
    done_reason: str | None
    prompt_eval_count: int | None
    eval_count: int | None
    total_duration_ns: int | None
    eval_duration_ns: int | None

    @property
    def complete(self) -> bool:
        return self.done and bool(self.content.strip()) and self.done_reason in {None, "stop"}

    @property
    def tokens_per_second(self) -> float | None:
        if not self.eval_count or not self.eval_duration_ns:
            return None
        seconds = self.eval_duration_ns / 1_000_000_000
        return self.eval_count / seconds if seconds > 0 else None


def _post(opener, url: str, data: dict, timeout: float) -> dict:
    req = request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    max_response = 8 * 1024 * 1024
    try:
        with opener.open(req, timeout=timeout) as response:
            raw = response.read(max_response + 1)
            if len(raw) > max_response:
                raise OllamaError("Ollama response exceeds size limit")
            body = json.loads(raw.decode("utf-8"))
    except (
        error.URLError,
        OSError,
        HTTPException,
        UnicodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise OllamaError(f"Local Ollama request failed ({type(exc).__name__})") from exc
    if not isinstance(body, dict) or "error" in body:
        raise OllamaError("Unexpected Ollama response structure")
    return body


def chat(
    base_url: str,
    model: str,
    system: str,
    user: str,
    *,
    num_ctx: int = 65_536,
    num_predict: int = 8_192,
    timeout: int = 3_600,
    think: bool | None = None,
) -> OllamaResult:
    base_url = validate_local_url(base_url)
    if (
        not isinstance(model, str)
        or not model.strip()
        or re.search(r"(?i)(?:^|[-:/])cloud$", model.strip())
    ):
        raise OllamaError("A locally installed model is required")
    deadline = time.monotonic() + timeout
    opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())
    # The loopback Ollama service can itself proxy a cloud-backed model.
    # Inspect model metadata before sending any evidence (including selector input).
    info = _post(opener, f"{base_url}/api/show", {"model": model}, min(timeout, 10))
    details = info.get("details")
    if (
        info.get("remote_host")
        or info.get("remote_model")
        or not (isinstance(details, dict) and details.get("format"))
    ):
        raise OllamaError("Ollama did not confirm local model weights")
    payload_data = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": redact(user)},
        ],
        "options": {
            "temperature": 0.1,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
    }
    if think is not None:
        payload_data["think"] = think
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise OllamaError("Local Ollama request timed out during model validation")
    body = _post(opener, f"{base_url}/api/chat", payload_data, remaining)
    message = body.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise OllamaError("Unexpected Ollama response structure")
    content = redact(message["content"].strip())

    return OllamaResult(
        content=content,
        done=body.get("done") is True,
        done_reason=body.get("done_reason") if isinstance(body.get("done_reason"), str) else None,
        prompt_eval_count=_optional_int(body.get("prompt_eval_count")),
        eval_count=_optional_int(body.get("eval_count")),
        total_duration_ns=_optional_int(body.get("total_duration")),
        eval_duration_ns=_optional_int(body.get("eval_duration")),
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None
