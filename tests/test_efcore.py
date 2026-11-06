from local_llm_code_auditor.efcore import audit


def _write_ef_project(root):
    (root / "App.csproj").write_text(
        """<Project Sdk="Microsoft.NET.Sdk">
<ItemGroup><PackageReference Include="Microsoft.EntityFrameworkCore.SqlServer" Version="10.0.0" /></ItemGroup>
</Project>""",
        encoding="utf-8",
    )
    (root / "AppDbContext.cs").write_text(
        "public class AppDbContext : DbContext {}", encoding="utf-8"
    )


def test_efcore_flags_migrations_without_snapshot(tmp_path):
    _write_ef_project(tmp_path)
    migrations = tmp_path / "Migrations"
    migrations.mkdir()
    (migrations / "202609021200_Init.cs").write_text("class Init {}", encoding="utf-8")
    result = audit(tmp_path)
    assert result.detected
    assert result.migration_files == ("Migrations/202609021200_Init.cs",)
    assert any(f.code == "EF_MISSING_MODEL_SNAPSHOT" for f in result.findings)


def test_efcore_flags_changed_snapshot_without_changed_migration(tmp_path):
    _write_ef_project(tmp_path)
    migrations = tmp_path / "Migrations"
    migrations.mkdir()
    (migrations / "202609021200_Init.cs").write_text("class Init {}", encoding="utf-8")
    (migrations / "AppDbContextModelSnapshot.cs").write_text(
        "class AppDbContextModelSnapshot {}", encoding="utf-8"
    )
    result = audit(tmp_path, " M Migrations/AppDbContextModelSnapshot.cs")
    assert any(f.code == "EF_SNAPSHOT_CHANGED_WITHOUT_MIGRATION" for f in result.findings)


def test_efcore_static_audit_never_claims_pending_model_check(tmp_path):
    _write_ef_project(tmp_path)
    result = audit(tmp_path)
    assert result.detected
    assert any(f.code == "EF_NO_LOCAL_MIGRATIONS" for f in result.findings)
    assert "NOT_RUN_STATIC_ONLY" in result.evidence_text()
