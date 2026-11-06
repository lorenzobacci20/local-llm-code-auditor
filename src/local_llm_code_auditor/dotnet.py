from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .process import CommandResult, run

_TEST_PACKAGE_HINTS = {
    "microsoft.net.test.sdk",
    "microsoft.testing.platform",
    "xunit",
    "nunit",
    "mstest.testframework",
}


@dataclass(slots=True)
class DotnetAudit:
    detected: bool
    build: CommandResult | None = None
    test: CommandResult | None = None
    test_projects: tuple[str, ...] = ()
    test_status: str = "NOT_APPLICABLE"


def detect(repo: Path) -> bool:
    return any(repo.glob("*.sln")) or any(repo.glob("*.slnx")) or any(repo.rglob("*.csproj"))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _looks_like_test_project(project: Path) -> bool:
    try:
        root = ET.parse(project).getroot()
    except (ET.ParseError, OSError):
        try:
            text = project.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            return False
        return (
            "<istestproject>true</istestproject>" in text
            or "microsoft.net.test.sdk" in text
            or "microsoft.testing.platform" in text
        )

    for element in root.iter():
        name = _local_name(element.tag)
        if name == "istestproject" and (element.text or "").strip().lower() == "true":
            return True
        if name == "packagereference":
            include = (
                (element.attrib.get("Include") or element.attrib.get("Update") or "")
                .strip()
                .lower()
            )
            if include in _TEST_PACKAGE_HINTS:
                return True
    return False


def discover_test_projects(repo: Path) -> tuple[Path, ...]:
    projects = [project for project in repo.rglob("*.csproj") if _looks_like_test_project(project)]
    return tuple(sorted(projects, key=lambda path: str(path).lower()))


def _run_test_projects(repo: Path, projects: tuple[Path, ...], timeout: int) -> CommandResult:
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    returncode = 0

    for project in projects:
        relative = project.relative_to(repo)
        result = run(
            ["dotnet", "test", str(relative), "--no-build", "--nologo", "--verbosity", "minimal"],
            repo,
            timeout,
        )
        stdout_parts.append(f"### {relative}\n{result.stdout}".rstrip())
        if result.stderr.strip():
            stderr_parts.append(f"### {relative}\n{result.stderr}".rstrip())
        if result.returncode != 0 and returncode == 0:
            returncode = result.returncode

    return CommandResult(
        ["dotnet", "test", "<detected-test-projects>", "--no-build"],
        returncode,
        "\n\n".join(part for part in stdout_parts if part),
        "\n\n".join(part for part in stderr_parts if part),
    )


def audit(repo: Path, timeout: int) -> DotnetAudit:
    if not detect(repo):
        return DotnetAudit(detected=False)

    test_projects = discover_test_projects(repo)
    relative_test_projects = tuple(str(project.relative_to(repo)) for project in test_projects)

    build = run(["dotnet", "build", "--nologo", "--verbosity", "minimal"], repo, timeout)
    if not build.ok:
        return DotnetAudit(
            detected=True,
            build=build,
            test_projects=relative_test_projects,
            test_status="SKIPPED_BUILD_FAILED",
        )

    if not test_projects:
        return DotnetAudit(
            detected=True,
            build=build,
            test_projects=(),
            test_status="SKIPPED_NO_TEST_PROJECTS",
        )

    test = _run_test_projects(repo, test_projects, timeout)
    return DotnetAudit(
        detected=True,
        build=build,
        test=test,
        test_projects=relative_test_projects,
        test_status="COMPLETED" if test.ok else "FAILED",
    )
