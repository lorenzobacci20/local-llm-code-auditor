import subprocess
from pathlib import Path

from local_llm_code_auditor.llm_review import (
    critic_user_prompt,
    followup_user_prompt,
    parse_followup_files,
    remaining_inventory,
)
from local_llm_code_auditor.source_review import collect, extend_with_followup


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "config", "user.name", "Local LLM Code Auditor Tests")


def test_followup_parser_only_accepts_allowlisted_paths():
    content = '["Services/RealService.cs", "../escape.cs", "C:\\\\Windows\\\\x.cs", "Unknown.cs"]'
    result = parse_followup_files(
        content,
        allowed_files=("Services/RealService.cs", "Models/Thing.cs"),
        already_selected=("Models/Thing.cs",),
        max_files=8,
    )
    assert result == ("Services/RealService.cs",)


def test_followup_parser_handles_fenced_json_and_limit():
    content = '```json\n["A.cs", "B.cs", "C.cs"]\n```'
    result = parse_followup_files(
        content,
        allowed_files=("A.cs", "B.cs", "C.cs"),
        already_selected=(),
        max_files=2,
    )
    assert result == ("A.cs", "B.cs")


def test_followup_inventory_excludes_already_selected(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    for name in ("Program.cs", "Services/A.cs", "Models/B.cs"):
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"// {name}\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")

    review = collect(repo, max_files=1, max_chars=10_000, max_file_chars=10_000)
    remaining = remaining_inventory(review)

    assert review.files[0] not in remaining
    assert set(remaining).issubset(set(review.candidate_files))


def test_extend_followup_reads_only_allowed_candidate(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "Program.cs").write_text("class Program {}\n", encoding="utf-8")
    (repo / "Services").mkdir()
    (repo / "Services" / "A.cs").write_text("class AService {}\n", encoding="utf-8")
    (repo / "Models").mkdir()
    (repo / "Models" / "B.cs").write_text("class B {}\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")

    review = collect(repo, max_files=1, max_chars=10_000, max_file_chars=10_000)
    candidate = next(path for path in review.candidate_files if path not in review.files)
    extended = extend_with_followup(
        repo,
        review,
        (candidate, "../escape.cs", "NotAllowed.cs"),
        total_max_chars=20_000,
        max_file_chars=10_000,
    )

    assert extended.followup_files == (candidate,)
    assert candidate in extended.files
    assert "../escape.cs" not in extended.text
    assert "NotAllowed.cs" not in extended.text


def test_followup_prompt_contains_allowlist_not_arbitrary_paths(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "Program.cs").write_text("class Program {}\n", encoding="utf-8")
    (repo / "Service.cs").write_text("class Service {}\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")

    review = collect(repo, max_files=1, max_chars=10_000, max_file_chars=10_000)
    prompt = followup_user_prompt("EVIDENCE", review, 8)

    assert "ALLOWLISTED REMAINING SOURCE FILES" in prompt
    for path in remaining_inventory(review):
        assert path in prompt


def test_critic_prompt_includes_draft_and_evidence():
    rendered = critic_user_prompt("EVIDENCE", "## Verdict\nGO")
    assert "EVIDENCE" in rendered
    assert "DRAFT AUDIT TO VERIFY" in rendered
    assert "## Verdict" in rendered
