from pathlib import Path
from unittest.mock import patch

from local_llm_code_auditor.dotnet import audit, discover_test_projects
from local_llm_code_auditor.process import CommandResult


def test_discovers_is_test_project(tmp_path: Path):
    app = tmp_path / "App.csproj"
    app.write_text(
        "<Project><PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup></Project>",
        encoding="utf-8",
    )
    test = tmp_path / "App.Tests.csproj"
    test.write_text(
        "<Project><PropertyGroup><IsTestProject>true</IsTestProject></PropertyGroup></Project>",
        encoding="utf-8",
    )

    assert discover_test_projects(tmp_path) == (test,)


def test_discovers_test_sdk_package(tmp_path: Path):
    test = tmp_path / "App.Tests.csproj"
    test.write_text(
        '<Project><ItemGroup><PackageReference Include="Microsoft.NET.Test.Sdk" Version="18.0.0" /></ItemGroup></Project>',
        encoding="utf-8",
    )

    assert discover_test_projects(tmp_path) == (test,)


def test_skips_dotnet_test_when_no_test_projects(tmp_path: Path):
    (tmp_path / "App.csproj").write_text("<Project />", encoding="utf-8")
    build_ok = CommandResult(["dotnet", "build"], 0, "ok", "")

    with patch("local_llm_code_auditor.dotnet.run", return_value=build_ok) as run_mock:
        result = audit(tmp_path, 10)

    assert result.test is None
    assert result.test_projects == ()
    assert result.test_status == "SKIPPED_NO_TEST_PROJECTS"
    assert run_mock.call_count == 1


def test_runs_each_detected_test_project(tmp_path: Path):
    (tmp_path / "App.csproj").write_text("<Project />", encoding="utf-8")
    test = tmp_path / "tests" / "App.Tests.csproj"
    test.parent.mkdir()
    test.write_text(
        "<Project><PropertyGroup><IsTestProject>true</IsTestProject></PropertyGroup></Project>",
        encoding="utf-8",
    )
    build_ok = CommandResult(["dotnet", "build"], 0, "build ok", "")
    test_ok = CommandResult(["dotnet", "test"], 0, "Passed! Total: 3", "")

    with patch("local_llm_code_auditor.dotnet.run", side_effect=[build_ok, test_ok]) as run_mock:
        result = audit(tmp_path, 10)

    assert result.test is not None and result.test.ok
    assert result.test_projects == (str(test.relative_to(tmp_path)),)
    assert result.test_status == "COMPLETED"
    assert run_mock.call_count == 2
    assert "App.Tests.csproj" in result.test.stdout
