# Local LLM Code Auditor Report — sample-app

Generated: 2026-11-24T13:49:25.519776+01:00

## Audit telemetry

- Repository: `sample-app`
- Branch: `main`
- HEAD: `793f6b74f5ca`
- Model: `qwen3.5:9b`
- Context requested: **16384 tokens**
- Max generated tokens: **4096**
- Project context status: **DISABLED**
- Project context root: `not available`
- Project context files: none
- Project context characters: **0**
- Project context truncated: **NO**
- Live evidence characters: **3295**
- Total user-prompt characters sent to audit LLM: **0**
- Audit input clipped to fit context: **NO**
- Selector paths offered: **0**
- Diff original characters: **0**
- Diff truncated: **NO**
- Build output original characters: **0**
- Build output truncated: **NO**
- .NET test projects detected: **0**
- .NET test projects: none
- .NET test execution status: **NOT_APPLICABLE**
- Test output original characters: **0**
- Test output truncated: **NO**
- ASP.NET analyzer: **DETECTED**
- ASP.NET deterministic findings: **3**
- EF Core analyzer: **NOT_DETECTED**
- EF Core migrations detected: **0**
- EF Core deterministic findings: **0**
- Source code review: **ENABLED**
- Source candidate files after filters: **2**
- Source budget characters: **31396**
- Source files reviewed: **1**
- Source categories reviewed: entrypoint
- Source follow-up selector: **SKIPPED_NO_LLM**
- Source follow-up files: none
- Source files: `Program.cs`
- Source original characters: **287**
- Source evidence truncated: **NO**
- Sensitive source lines redacted: **0**
- Audit LLM response: **SKIPPED**
- Critic pass: **SKIPPED_NO_LLM**
- Final report source: **NONE**

## Deterministic analyzer findings

### ASP.NET
- MEDIUM [ASPNET_PROD_DETAILED_ERRORS] `appsettings.Production.json`: Production configuration enables \`DetailedErrors=true\`.
- MEDIUM [ASPNET_PROD_LOCALHOST] `appsettings.Production.json`: Production configuration key \`Api:BaseUrl\` points to localhost/loopback.
- LOW [ASPNET_PROD_VERBOSE_LOGGING] `appsettings.Production.json`: Production logging key \`Logging:LogLevel:Default\` is set to \`Debug\`.

### EF Core
- No deterministic findings.

## Repository: sample-app

```text
## Verdict
WARNING

## Findings
- INFO: LLM analysis skipped. Deterministic and bounded source evidence were collected only.

## Suggested actions
Inspect deterministic analyzer findings, selected source evidence, and build/test evidence manually.
```

---

Local LLM Code Auditor report completed successfully.
