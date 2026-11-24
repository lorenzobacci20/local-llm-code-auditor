"""Best-effort secret masking at collection and model/report boundaries."""

from __future__ import annotations

import re

_MASK = "[REDACTED]"
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
_END_KEY = re.compile(r"-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
# Drop the entire line so quotes, escaping and connection-string separators
# cannot leave part of the matched value in the evidence.
_ASSIGNMENT = re.compile(
    r"""(?ix)(?:password|passwd|\bpwd|secret|token|api[_-]?key|private[_-]?key|
        signing[_-]?key|account[_-]?key|sharedaccess(?:signature|key)|
        connection[_-]?string|authorization|set-cookie|\bcookie)
        ["']?\s*[:=]"""
)
_AUTH_VALUE = re.compile(r"(?i)\b(?:bearer|basic)[ \t]+[A-Za-z0-9+/._=~-]{6,}")
_CREDENTIAL_URI = re.compile(r"""(?i)\b[a-z][a-z0-9+.-]*://[^/\s@"'<>]+@""")
_TOKEN = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|"
    r"sk-[A-Za-z0-9_-]{16,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"(?:AKIA|ASIA)[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)"
)


def redact_with_count(text: str) -> tuple[str, int]:
    """Preserve line boundaries and return the number of lines replaced."""
    output: list[str] = []
    count = 0
    in_key = False
    continuation = False
    block_indent: int | None = None
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        # Unified diffs prefix added, removed and context lines.
        logical = content.removeprefix("+").removeprefix("-")
        indent = len(logical) - len(logical.lstrip())
        in_block = block_indent is not None and (not logical.strip() or indent > block_indent)
        if not in_block:
            block_indent = None
        assignment = _ASSIGNMENT.search(content)
        in_key = in_key or bool(_PRIVATE_KEY.search(content))
        sensitive = (
            in_key
            or continuation
            or in_block
            or bool(assignment)
            or bool(
                _AUTH_VALUE.search(content)
                or _CREDENTIAL_URI.search(content)
                or _TOKEN.search(content)
            )
        )
        if sensitive:
            output.append(_MASK + line[len(content) :])
            count += 1
        else:
            output.append(line)
        if _END_KEY.search(content):
            in_key = False
        if assignment:
            tail = content[assignment.end() :].strip()
            continuation = not tail
            if re.fullmatch(r"[|>][-+]?\d*", tail):
                block_indent = indent
        elif logical.strip():
            continuation = False
    return "".join(output), count


def redact(text: str) -> str:
    return redact_with_count(text)[0]
