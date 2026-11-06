from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .static_analysis import StaticFinding, is_ignored_path, relative_path

_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "clientsecret",
    "apikey",
    "api_key",
    "accesstoken",
    "refreshtoken",
    "token",
    "privatekey",
    "accountkey",
)
_CONNECTION_SECRET_RE = re.compile(
    r"(?i)(?:password|pwd|accountkey|sharedaccesskey|clientsecret)\s*="
)
_PLACEHOLDER_RE = re.compile(
    r"^(?:|\$\{.+\}|%\w+%|__.+__|<.+>|#\{.+\}#|changeme|change-me|todo|redacted)$",
    re.IGNORECASE,
)
_LOCALHOST_RE = re.compile(r"(?i)(?:localhost|127\.0\.0\.1|\[::1\])")


@dataclass(slots=True)
class AspNetAudit:
    detected: bool
    projects: tuple[str, ...] = ()
    config_files: tuple[str, ...] = ()
    findings: tuple[StaticFinding, ...] = ()

    def evidence_text(self) -> str:
        lines = [
            "ASP.NET static analyzer:",
            f"ASP.NET detected: {'YES' if self.detected else 'NO'}",
            f"ASP.NET web projects: {len(self.projects)}",
            "ASP.NET project files: " + (", ".join(self.projects) if self.projects else "none"),
            f"ASP.NET appsettings files: {len(self.config_files)}",
            "ASP.NET config files: "
            + (", ".join(self.config_files) if self.config_files else "none"),
            f"ASP.NET deterministic findings: {len(self.findings)}",
        ]
        lines.extend(f.render() for f in self.findings)
        return "\n".join(lines)


def _web_project(project: Path) -> bool:
    try:
        root = ET.parse(project).getroot()
    except (ET.ParseError, OSError):
        try:
            text = project.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            return False
        return "microsoft.net.sdk.web" in text or "microsoft.aspnetcore.app" in text

    sdk = (root.attrib.get("Sdk") or "").lower()
    if "microsoft.net.sdk.web" in sdk:
        return True
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1].lower()
        if name == "frameworkreference":
            include = (element.attrib.get("Include") or "").lower()
            if include == "microsoft.aspnetcore.app":
                return True
        if name == "sdk":
            name_attr = (element.attrib.get("Name") or "").lower()
            if "microsoft.net.sdk.web" in name_attr:
                return True
    return False


def _iter_web_projects(repo: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (p for p in repo.rglob("*.csproj") if not is_ignored_path(p) and _web_project(p)),
            key=lambda p: str(p).lower(),
        )
    )


def _iter_appsettings(repo: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (p for p in repo.rglob("appsettings*.json") if p.is_file() and not is_ignored_path(p)),
            key=lambda p: str(p).lower(),
        )
    )


def _strip_json_comments(text: str) -> str:
    """Strip JavaScript/C# comments while preserving strings and line structure."""
    out: list[str] = []
    i = 0
    in_string = False
    escaped = False
    block_comment_start: int | None = None

    while i < len(text):
        char = text[i]

        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            i += 1
            continue

        if char == '"':
            in_string = True
            out.append(char)
            i += 1
            continue

        if char == "/" and i + 1 < len(text):
            next_char = text[i + 1]
            if next_char == "/":
                out.extend((" ", " "))
                i += 2
                while i < len(text) and text[i] not in "\r\n":
                    out.append(" ")
                    i += 1
                continue
            if next_char == "*":
                block_comment_start = i
                out.extend((" ", " "))
                i += 2
                while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                    out.append(text[i] if text[i] in "\r\n" else " ")
                    i += 1
                if i + 1 >= len(text):
                    raise json.JSONDecodeError(
                        "Unterminated block comment", text, block_comment_start
                    )
                out.extend((" ", " "))
                i += 2
                block_comment_start = None
                continue

        out.append(char)
        i += 1

    return "".join(out)


def _strip_trailing_commas(text: str) -> str:
    """Remove commas before } or ] outside strings, matching ASP.NET JSON tolerance."""
    out: list[str] = []
    i = 0
    in_string = False
    escaped = False

    while i < len(text):
        char = text[i]

        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            i += 1
            continue

        if char == '"':
            in_string = True
            out.append(char)
            i += 1
            continue

        if char == ",":
            lookahead = i + 1
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(text) and text[lookahead] in "}]":
                i += 1
                continue

        out.append(char)
        i += 1

    return "".join(out)


def _load_appsettings(config: Path) -> object:
    text = config.read_text(encoding="utf-8-sig")
    return json.loads(_strip_trailing_commas(_strip_json_comments(text)))


def _is_placeholder(value: str) -> bool:
    return bool(_PLACEHOLDER_RE.match(value.strip()))


def _walk_values(value: object, prefix: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}:{key}" if prefix else str(key)
            yield from _walk_values(child, child_prefix)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            yield from _walk_values(child, f"{prefix}[{idx}]")
    else:
        yield prefix, value


def _normalized_key(path: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", path.lower())


def audit(repo: Path) -> AspNetAudit:
    projects = _iter_web_projects(repo)
    if not projects:
        return AspNetAudit(detected=False)

    configs = _iter_appsettings(repo)
    findings: list[StaticFinding] = []

    for config in configs:
        rel = relative_path(repo, config)
        is_production = config.name.lower() == "appsettings.production.json"
        try:
            data = _load_appsettings(config)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            findings.append(
                StaticFinding(
                    "ASP.NET",
                    "MEDIUM",
                    "ASPNET_CONFIG_PARSE",
                    rel,
                    f"Configuration file could not be parsed as ASP.NET JSON configuration ({type(exc).__name__}); runtime configuration loading may fail.",
                )
            )
            continue

        for key_path, raw in _walk_values(data):
            norm = _normalized_key(key_path)
            if isinstance(raw, str):
                if any(part in norm for part in _SENSITIVE_KEY_PARTS):
                    if raw.strip() and not _is_placeholder(raw):
                        findings.append(
                            StaticFinding(
                                "ASP.NET",
                                "HIGH",
                                "ASPNET_HARDCODED_SECRET",
                                rel,
                                f"Possible hardcoded sensitive value at configuration key `{key_path}`. Value was redacted by Local LLM Code Auditor.",
                            )
                        )
                elif "connectionstrings" in norm and _CONNECTION_SECRET_RE.search(raw):
                    findings.append(
                        StaticFinding(
                            "ASP.NET",
                            "HIGH",
                            "ASPNET_CONNECTION_SECRET",
                            rel,
                            f"Connection string key `{key_path}` appears to contain an embedded credential. Value was redacted by Local LLM Code Auditor.",
                        )
                    )

                if is_production and _LOCALHOST_RE.search(raw):
                    key_lower = key_path.lower()
                    if any(
                        hint in key_lower
                        for hint in ("url", "uri", "endpoint", "baseaddress", "host")
                    ):
                        findings.append(
                            StaticFinding(
                                "ASP.NET",
                                "MEDIUM",
                                "ASPNET_PROD_LOCALHOST",
                                rel,
                                f"Production configuration key `{key_path}` points to localhost/loopback.",
                            )
                        )

                if is_production and raw.strip().lower() in {"debug", "trace"}:
                    if "logging:loglevel" in key_path.lower():
                        findings.append(
                            StaticFinding(
                                "ASP.NET",
                                "LOW",
                                "ASPNET_PROD_VERBOSE_LOGGING",
                                rel,
                                f"Production logging key `{key_path}` is set to `{raw.strip()}`.",
                            )
                        )

            if is_production and isinstance(raw, bool) and raw:
                if key_path.lower().endswith("detailederrors"):
                    findings.append(
                        StaticFinding(
                            "ASP.NET",
                            "MEDIUM",
                            "ASPNET_PROD_DETAILED_ERRORS",
                            rel,
                            f"Production configuration enables `{key_path}=true`.",
                        )
                    )

    unique = {(f.severity, f.code, f.path, f.message): f for f in findings}
    ordered = tuple(sorted(unique.values(), key=lambda f: (f.path.lower(), f.code, f.message)))
    return AspNetAudit(
        detected=True,
        projects=tuple(relative_path(repo, p) for p in projects),
        config_files=tuple(relative_path(repo, p) for p in configs),
        findings=ordered,
    )
