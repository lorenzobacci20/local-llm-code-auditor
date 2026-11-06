import subprocess
from pathlib import Path

from local_llm_code_auditor.source_review import adaptive_source_budget, collect


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "config", "user.name", "Local LLM Code Auditor Tests")


def test_source_review_prioritizes_changed_source(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "Program.cs").write_text("class Program { static void Main() {} }\n", encoding="utf-8")
    _git(repo, "add", "Program.cs")
    _git(repo, "commit", "-m", "baseline")

    (repo / "Feature.cs").write_text("class Feature { int Value => 42; }\n", encoding="utf-8")

    review = collect(repo, max_files=1, max_chars=10_000, max_file_chars=10_000)

    assert review.files == ("Feature.cs",)
    assert "class Feature" in review.text


def test_source_review_preserves_sensitive_literals_for_local_model(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    secret = "local-review-secret-value"
    (repo / "SecurityService.cs").write_text(
        f'class SecurityService {{ private const string ApiKey = "{secret}"; }}\n',
        encoding="utf-8",
    )

    review = collect(repo, max_files=2, max_chars=10_000, max_file_chars=10_000)

    assert secret in review.text
    assert "REDACTED" not in review.text
    assert "DISABLED_LOCAL_OLLAMA_TRUST_BOUNDARY" in review.evidence_text()


def test_source_review_respects_total_budget(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "Program.cs").write_text("x" * 5_000, encoding="utf-8")

    review = collect(repo, max_files=1, max_chars=1_000, max_file_chars=4_000)

    assert review.truncated is True
    assert len(review.text) <= 1_100
    assert review.budget_chars == 1_000


def test_source_review_excludes_vendor_and_unchanged_generated_code(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "Program.cs").write_text("class Program {}\n", encoding="utf-8")
    vendor = repo / "wwwroot" / "lib" / "sample-vendor"
    vendor.mkdir(parents=True)
    (vendor / "event-handler.js").write_text("export const vendor = true;\n", encoding="utf-8")
    migrations = repo / "Migrations"
    migrations.mkdir()
    (migrations / "AppDbContextModelSnapshot.cs").write_text(
        "class Snapshot {}\n", encoding="utf-8"
    )

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")

    review = collect(repo, max_files=16, max_chars=96_000, max_file_chars=16_000)

    assert "Program.cs" in review.files
    assert not any("wwwroot/lib" in path for path in review.files)
    assert not any("ModelSnapshot" in path for path in review.files)


def test_source_review_prefers_architectural_diversity(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "Program.cs").write_text("class Program {}\n", encoding="utf-8")
    controllers = repo / "Controllers"
    controllers.mkdir()
    for index in range(8):
        (controllers / f"Controller{index}.cs").write_text(
            f"class Controller{index} {{}}\n", encoding="utf-8"
        )
    services = repo / "Services"
    services.mkdir()
    (services / "ProjectService.cs").write_text("class ProjectService {}\n", encoding="utf-8")
    data = repo / "Data"
    data.mkdir()
    (data / "AppDbContext.cs").write_text("class AppDbContext {}\n", encoding="utf-8")
    models = repo / "Models"
    models.mkdir()
    (models / "Project.cs").write_text("class Project {}\n", encoding="utf-8")

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")

    review = collect(repo, max_files=5, max_chars=96_000, max_file_chars=16_000)

    assert "Program.cs" in review.files
    assert any("Controller" in path for path in review.files)
    assert "Services/ProjectService.cs" in review.files
    assert "Data/AppDbContext.cs" in review.files
    assert "Models/Project.cs" in review.files
    assert set(("entrypoint", "api", "service", "data", "domain")).issubset(set(review.categories))


def test_source_review_keeps_changed_migration_context(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    migrations = repo / "Migrations"
    migrations.mkdir()
    migration = migrations / "20260903120000_AddThing.cs"
    migration.write_text("class AddThing { void Up() {} }\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")

    migration.write_text("class AddThing { void Up() { /* changed */ } }\n", encoding="utf-8")

    review = collect(repo, max_files=2, max_chars=20_000, max_file_chars=10_000)

    assert "Migrations/20260903120000_AddThing.cs" in review.files


def test_adaptive_source_budget_uses_headroom_and_clamps_to_config():
    budget = adaptive_source_budget(
        num_ctx=65_536,
        num_predict=8_192,
        base_prompt_chars=20_000,
        configured_max_chars=96_000,
    )

    assert budget == 96_000


def test_adaptive_source_budget_shrinks_for_large_base_prompt():
    budget = adaptive_source_budget(
        num_ctx=65_536,
        num_predict=8_192,
        base_prompt_chars=150_000,
        configured_max_chars=96_000,
    )

    assert 0 <= budget < 20_000
