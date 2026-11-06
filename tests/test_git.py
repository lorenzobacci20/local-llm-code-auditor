import subprocess
from pathlib import Path

from local_llm_code_auditor.git import discover_repositories


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)


def test_discover_repositories(tmp_path: Path):
    repo = tmp_path / "a"
    _init_repo(repo)

    assert discover_repositories([tmp_path]) == [repo.resolve()]


def test_discover_repositories_excludes_deploy_copies(tmp_path: Path):
    source = tmp_path / "SampleLibrary"
    deploy = tmp_path / "deploy" / "SampleLibrary"
    deploy_test = tmp_path / "deploy-test4" / "SampleLibrary"
    _init_repo(source)
    _init_repo(deploy)
    _init_repo(deploy_test)

    assert discover_repositories([tmp_path]) == [source.resolve()]
