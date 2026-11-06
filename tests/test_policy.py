from local_llm_code_auditor.report import SYSTEM_PROMPT


def test_system_prompt_forbids_pending_migration_inference_and_db_update():
    lower = SYSTEM_PROMPT.lower()
    assert "do not establish which migrations are applied or pending" in lower
    assert "never recommend `dotnet ef database update`" in lower
    assert "read-only with respect to databases" in lower
