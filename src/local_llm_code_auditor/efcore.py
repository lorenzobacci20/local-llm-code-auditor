from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .static_analysis import StaticFinding, is_ignored_path, relative_path

_EF_PACKAGE_PREFIX = "microsoft.entityframeworkcore"
_DBCONTEXT_RE = re.compile(r"\bclass\s+\w+\s*:\s*[^{\n]*\bDbContext\b")
_MIGRATION_RE = re.compile(r"^(\d{8,})_(.+)\.cs$", re.IGNORECASE)


@dataclass(slots=True)
class EfCoreAudit:
    detected: bool
    projects: tuple[str, ...] = ()
    packages: tuple[str, ...] = ()
    dbcontext_files: tuple[str, ...] = ()
    migration_files: tuple[str, ...] = ()
    snapshot_files: tuple[str, ...] = ()
    findings: tuple[StaticFinding, ...] = ()

    def evidence_text(self) -> str:
        latest = self.migration_files[-1] if self.migration_files else "none"
        lines = [
            "EF Core static analyzer:",
            f"EF Core detected: {'YES' if self.detected else 'NO'}",
            f"EF Core projects: {len(self.projects)}",
            "EF Core project files: " + (", ".join(self.projects) if self.projects else "none"),
            "EF Core packages: " + (", ".join(self.packages) if self.packages else "none"),
            f"DbContext source files: {len(self.dbcontext_files)}",
            "DbContext files: "
            + (", ".join(self.dbcontext_files) if self.dbcontext_files else "none"),
            f"EF migration files: {len(self.migration_files)}",
            f"EF latest migration source artifact: {latest}",
            f"EF model snapshots: {len(self.snapshot_files)}",
            "EF snapshot files: "
            + (", ".join(self.snapshot_files) if self.snapshot_files else "none"),
            "EF database applied/pending migration state: NOT_CHECKED_NO_DATABASE_CONNECTION",
            "EF model-vs-migrations runtime validation: NOT_RUN_STATIC_ONLY",
            "EF safety boundary: READ_ONLY_STATIC_ANALYSIS; no database migration command was executed",
            f"EF deterministic findings: {len(self.findings)}",
        ]
        lines.extend(f.render() for f in self.findings)
        return "\n".join(lines)


def _package_references(project: Path) -> tuple[str, ...]:
    packages: set[str] = set()
    try:
        root = ET.parse(project).getroot()
    except (ET.ParseError, OSError):
        try:
            text = project.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ()
        for match in re.finditer(
            r'PackageReference[^>]+Include=["\']([^"\']+)["\']', text, re.IGNORECASE
        ):
            packages.add(match.group(1))
        return tuple(sorted(packages, key=str.lower))

    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1].lower()
        if name == "packagereference":
            include = (element.attrib.get("Include") or element.attrib.get("Update") or "").strip()
            if include:
                packages.add(include)
    return tuple(sorted(packages, key=str.lower))


def _changed_paths(status: str) -> set[str]:
    result: set[str] = set()
    for line in status.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path:
            result.add(path.replace("\\", "/"))
    return result


def audit(repo: Path, git_status: str = "") -> EfCoreAudit:
    projects: list[str] = []
    package_names: set[str] = set()
    for project in repo.rglob("*.csproj"):
        if is_ignored_path(project):
            continue
        packages = _package_references(project)
        ef_packages = [p for p in packages if p.lower().startswith(_EF_PACKAGE_PREFIX)]
        if ef_packages:
            projects.append(relative_path(repo, project))
            package_names.update(ef_packages)

    dbcontexts: list[str] = []
    for source in repo.rglob("*.cs"):
        if is_ignored_path(source):
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _DBCONTEXT_RE.search(text):
            dbcontexts.append(relative_path(repo, source))

    detected = bool(projects or dbcontexts)
    if not detected:
        return EfCoreAudit(detected=False)

    migrations: list[tuple[str, str]] = []
    snapshots: list[str] = []
    findings: list[StaticFinding] = []

    for source in repo.rglob("*.cs"):
        if is_ignored_path(source):
            continue
        rel = relative_path(repo, source)
        if not any(part.lower() == "migrations" for part in source.parts):
            continue
        if source.name.endswith("ModelSnapshot.cs"):
            snapshots.append(rel)
            continue
        if source.name.endswith(".Designer.cs"):
            continue
        match = _MIGRATION_RE.match(source.name)
        if match:
            migrations.append((match.group(1), rel))
            try:
                text = source.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            if "throw new NotImplementedException" in text:
                findings.append(
                    StaticFinding(
                        "EF Core",
                        "HIGH",
                        "EF_MIGRATION_NOT_IMPLEMENTED",
                        rel,
                        "Migration contains `throw new NotImplementedException`, which would make migration execution fail.",
                    )
                )

    migration_ids: dict[str, list[str]] = {}
    for migration_id, rel in migrations:
        migration_ids.setdefault(migration_id, []).append(rel)
    for migration_id, paths in migration_ids.items():
        if len(paths) > 1:
            findings.append(
                StaticFinding(
                    "EF Core",
                    "HIGH",
                    "EF_DUPLICATE_MIGRATION_ID",
                    paths[0],
                    f"Migration id `{migration_id}` is duplicated across {len(paths)} migration files.",
                )
            )

    if migrations and not snapshots:
        findings.append(
            StaticFinding(
                "EF Core",
                "MEDIUM",
                "EF_MISSING_MODEL_SNAPSHOT",
                migrations[-1][1],
                "EF Core migrations exist but no `*ModelSnapshot.cs` file was found.",
            )
        )

    changed = _changed_paths(git_status)
    changed_snapshots = [p for p in snapshots if p.replace("\\", "/") in changed]
    changed_migrations = [p for _, p in migrations if p.replace("\\", "/") in changed]
    if changed_snapshots and not changed_migrations:
        findings.append(
            StaticFinding(
                "EF Core",
                "MEDIUM",
                "EF_SNAPSHOT_CHANGED_WITHOUT_MIGRATION",
                changed_snapshots[0],
                "A tracked EF model snapshot changed while no migration source file is changed in the working tree.",
            )
        )

    if dbcontexts and not migrations:
        findings.append(
            StaticFinding(
                "EF Core",
                "INFO",
                "EF_NO_LOCAL_MIGRATIONS",
                dbcontexts[0],
                "DbContext source was detected but no local migration files were found. This may be intentional when migrations are managed elsewhere.",
            )
        )

    migration_paths = tuple(
        rel for _, rel in sorted(migrations, key=lambda item: (item[0], item[1].lower()))
    )
    ordered_findings = tuple(sorted(findings, key=lambda f: (f.severity, f.path.lower(), f.code)))
    return EfCoreAudit(
        detected=True,
        projects=tuple(sorted(projects, key=str.lower)),
        packages=tuple(sorted(package_names, key=str.lower)),
        dbcontext_files=tuple(sorted(dbcontexts, key=str.lower)),
        migration_files=migration_paths,
        snapshot_files=tuple(sorted(snapshots, key=str.lower)),
        findings=ordered_findings,
    )
