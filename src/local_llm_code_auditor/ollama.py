from __future__ import annotations

import json
from dataclasses import dataclass
from ipaddress import ip_address
from urllib import error, request
from urllib.parse import urlsplit


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
        return self.done and self.done_reason not in {"length", "limit"}

    @property
    def tokens_per_second(self) -> float | None:
        if not self.eval_count or not self.eval_duration_ns:
            return None
        seconds = self.eval_duration_ns / 1_000_000_000
        return self.eval_count / seconds if seconds > 0 else None


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
    payload_data = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {
            "temperature": 0.1,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
    }
    if think is not None:
        payload_data["think"] = think
    payload = json.dumps(payload_data).encode("utf-8")

    req = request.Request(
        f"{base_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())
        with opener.open(req, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (error.URLError, TimeoutError, UnicodeError, json.JSONDecodeError) as exc:
        raise OllamaError(f"Local Ollama request failed ({type(exc).__name__})") from exc

    try:
        content = body["message"]["content"].strip()
    except (KeyError, TypeError, AttributeError) as exc:
        raise OllamaError("Unexpected Ollama response structure") from exc

    return OllamaResult(
        content=content,
        done=body.get("done") is True,
        done_reason=body.get("done_reason"),
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
    except (TypeError, ValueError):
        return None
