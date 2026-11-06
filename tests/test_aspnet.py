from local_llm_code_auditor.aspnet import audit


def _write_web_project(root):
    project = root / "Web"
    project.mkdir()
    (project / "Web.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk.Web"></Project>', encoding="utf-8"
    )
    return project


def test_aspnet_analyzer_redacts_secrets_and_flags_production_risks(tmp_path):
    project = _write_web_project(tmp_path)
    secret = "do-not-leak-this-secret"
    (project / "appsettings.Production.json").write_text(
        """{
  "DetailedErrors": true,
  "Api": {"ClientSecret": "%s", "BaseUrl": "http://localhost:5000"},
  "ConnectionStrings": {"Default": "Server=db;User Id=app;Password=hidden;"}
}"""
        % secret,
        encoding="utf-8",
    )

    result = audit(tmp_path)

    assert result.detected
    codes = {finding.code for finding in result.findings}
    assert "ASPNET_HARDCODED_SECRET" in codes
    assert "ASPNET_CONNECTION_SECRET" in codes
    assert "ASPNET_PROD_LOCALHOST" in codes
    assert "ASPNET_PROD_DETAILED_ERRORS" in codes
    rendered = result.evidence_text()
    assert secret not in rendered
    assert "Password=hidden" not in rendered


def test_aspnet_analyzer_accepts_comments_and_trailing_commas(tmp_path):
    project = _write_web_project(tmp_path)
    (project / "appsettings.json").write_text(
        """{
  // ASP.NET supports JavaScript/C# style comments.
  "AllowedHosts": "*",
  "Api": {
    "BaseUrl": "https://example.test/a//b",
    "Literal": "/* this is part of the string */",
  },
  /* Block comments are valid for ASP.NET configuration too. */
  "Features": [
    "one",
    "two",
  ],
}""",
        encoding="utf-8",
    )

    result = audit(tmp_path)

    assert result.detected
    assert "ASPNET_CONFIG_PARSE" not in {finding.code for finding in result.findings}


def test_aspnet_analyzer_still_flags_invalid_configuration(tmp_path):
    project = _write_web_project(tmp_path)
    (project / "appsettings.json").write_text(
        '{"Logging": {"LogLevel": {"Default": "Information"}',
        encoding="utf-8",
    )

    result = audit(tmp_path)

    assert "ASPNET_CONFIG_PARSE" in {finding.code for finding in result.findings}


def test_non_web_project_does_not_trigger_aspnet_analyzer(tmp_path):
    (tmp_path / "Lib.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk"></Project>', encoding="utf-8"
    )
    assert not audit(tmp_path).detected
