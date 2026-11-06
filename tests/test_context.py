from pathlib import Path

from local_llm_code_auditor.context import (
    compose_llm_input,
    discover_context_root,
    load_context,
)


def test_does_not_discover_sibling_context_implicitly(tmp_path: Path):
    work = tmp_path / "Projects"
    context_root = work / "project-context"
    context_root.mkdir(parents=True)
    (context_root / "AGENTS.md").write_text("policy", encoding="utf-8")

    found = discover_context_root(None, [work], work / "local-llm-code-auditor" / "agent.toml")

    assert found is None
    assert (
        discover_context_root(context_root, [work], work / "agent.toml") == context_root.resolve()
    )


def test_loads_only_root_policy_and_matching_project_context(tmp_path: Path):
    root = tmp_path / "project-context"
    project = root / "projects" / "sample-app"
    project.mkdir(parents=True)
    (root / "AGENTS.md").write_text("root policy", encoding="utf-8")
    (project / "current-state.md").write_text("current project state", encoding="utf-8")
    (project / "architecture.md").write_text("project architecture", encoding="utf-8")
    unrelated = root / "finance"
    unrelated.mkdir()
    (unrelated / "current.md").write_text("unrelated finance context", encoding="utf-8")

    bundle = load_context(root, "SampleApp", 24_000)

    assert bundle.status == "LOADED"
    assert bundle.files == (
        "AGENTS.md",
        "projects/sample-app/current-state.md",
        "projects/sample-app/architecture.md",
    )
    assert "root policy" in bundle.text
    assert "current project state" in bundle.text
    assert "unrelated finance context" not in bundle.text


def test_matches_project_by_repository_frontmatter_when_slug_differs(tmp_path: Path):
    root = tmp_path / "project-context"
    project = root / "projects" / "friendly-name"
    project.mkdir(parents=True)
    (root / "AGENTS.md").write_text("policy", encoding="utf-8")
    (project / "current-state.md").write_text(
        "---\nrepository: example/SampleApp\n---\nproject state",
        encoding="utf-8",
    )

    bundle = load_context(root, "SampleApp", 24_000)

    assert "projects/friendly-name/current-state.md" in bundle.files
    assert "project state" in bundle.text


def test_compose_input_keeps_live_evidence_after_durable_context(tmp_path: Path):
    root = tmp_path / "project-context"
    root.mkdir()
    (root / "AGENTS.md").write_text("durable policy", encoding="utf-8")
    bundle = load_context(root, "repo", 24_000)

    prompt = compose_llm_input(bundle, "LIVE EVIDENCE")

    assert "durable policy" in prompt
    assert prompt.endswith("LIVE EVIDENCE")
    assert prompt.index("durable policy") < prompt.index("LIVE EVIDENCE")
