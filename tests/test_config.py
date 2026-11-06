from pathlib import Path

import pytest

from local_llm_code_auditor.config import load_config


def test_load_config_uses_effectiveness_first_defaults(tmp_path: Path):
    p = tmp_path / "agent.toml"
    p.write_text('[agent]\nroots=["~/Code"]\nmodel="x"\n', encoding="utf-8")

    cfg = load_config(p)

    assert cfg.model == "x"
    assert len(cfg.roots) == 1
    assert cfg.num_ctx == 65_536
    assert cfg.num_predict == 8_192
    assert cfg.max_diff_chars == 120_000
    assert cfg.max_command_output_chars == 24_000
    assert cfg.llm_timeout_seconds == 3_600
    assert "deploy" in cfg.discovery_exclude_dirs
    assert "deploy-*" in cfg.discovery_exclude_dirs
    assert cfg.context_enabled is False
    assert cfg.context_path is None
    assert cfg.context_max_chars == 24_000
    assert cfg.source_review_enabled is True
    assert cfg.source_review_max_chars == 96_000
    assert cfg.source_review_max_files == 16
    assert cfg.source_review_max_file_chars == 16_000
    assert cfg.source_review_followup_enabled is True
    assert cfg.source_review_followup_max_files == 8
    assert cfg.source_review_followup_max_chars == 48_000
    assert cfg.source_review_critic_enabled is True


def test_load_config_reads_context_section_and_resolves_relative_path(tmp_path: Path):
    p = tmp_path / "agent.toml"
    p.write_text(
        '[agent]\nroots=["C:/Projects"]\n\n'
        '[context]\nenabled=true\npath="../project-context"\nmax_chars=32000\n',
        encoding="utf-8",
    )

    cfg = load_config(p)

    assert cfg.context_enabled is True
    assert cfg.context_path == tmp_path.resolve().parent / "project-context"
    assert cfg.context_max_chars == 32_000


def test_load_config_reads_source_review_and_discovery_overrides(tmp_path: Path):
    p = tmp_path / "agent.toml"
    p.write_text(
        '[agent]\nroots=["C:/Projects"]\ndiscovery_exclude_dirs=["deploy-*", "publish"]\n\n'
        "[source_review]\nenabled=false\nmax_chars=20000\nmax_files=4\nmax_file_chars=6000\n"
        "followup_enabled=false\nfollowup_max_files=3\nfollowup_max_chars=12000\ncritic_enabled=false\n",
        encoding="utf-8",
    )

    cfg = load_config(p)

    assert cfg.discovery_exclude_dirs == ("deploy-*", "publish")
    assert cfg.source_review_enabled is False
    assert cfg.source_review_max_chars == 20_000
    assert cfg.source_review_max_files == 4
    assert cfg.source_review_max_file_chars == 6_000
    assert cfg.source_review_followup_enabled is False
    assert cfg.source_review_followup_max_files == 3
    assert cfg.source_review_followup_max_chars == 12_000
    assert cfg.source_review_critic_enabled is False


def test_load_config_rejects_non_positive_context(tmp_path: Path):
    p = tmp_path / "agent.toml"
    p.write_text("[agent]\nnum_ctx=0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="num_ctx must be > 0"):
        load_config(p)


def test_thinking_defaults_to_model_and_accepts_explicit_boolean(tmp_path: Path):
    p = tmp_path / "agent.toml"
    p.write_text("[agent]\n", encoding="utf-8")
    assert load_config(p).think is None
    p.write_text("[agent]\nthink=false\n", encoding="utf-8")
    assert load_config(p).think is False
    p.write_text('[agent]\nthink="false"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="think must be a boolean"):
        load_config(p)
