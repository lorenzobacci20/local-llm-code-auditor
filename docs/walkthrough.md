# Walkthrough: inspect the evidence behind a review

This example uses only the public synthetic fixture in
[`examples/synthetic-repo`](../examples/synthetic-repo). It shows what the tool
can establish deterministically and what still needs model or human judgment.

## 1. Start with a small, inspectable input

The sample's `appsettings.Production.json` contains:

```json
{
  "DetailedErrors": true,
  "Api": { "BaseUrl": "http://localhost:5000" },
  "Logging": { "LogLevel": { "Default": "Debug" } }
}
```

These values are deliberately chosen to exercise three configuration rules.
The sample contains no real credentials, customer data or private infrastructure.

## 2. Run the real CLI through the demo

From an installed checkout:

```sh
python scripts/demo.py
```

The script creates a temporary Git repository, runs the CLI with `--no-llm` and
`--skip-build`, prints the report and checks that the expected rule IDs appear.
It then removes that temporary workspace. To keep a run in a **new** directory:

```sh
python scripts/demo.py --output demo-workspace
```

No Ollama model, API key, .NET SDK or database is needed for this path.

## 3. Read the findings and their scope

The [recorded example report](example-report.md) contains:

| Rule | Observation | What it does not establish |
| --- | --- | --- |
| `ASPNET_PROD_DETAILED_ERRORS` | The production configuration enables detailed errors. | Whether this configuration is deployed or an error page is publicly reachable. |
| `ASPNET_PROD_LOCALHOST` | A production endpoint points to loopback. | Whether a same-host service is intentional in the real deployment. |
| `ASPNET_PROD_VERBOSE_LOGGING` | The production logging level is `Debug`. | Whether sensitive values have actually appeared in logs. |

These are rule-based findings to inspect in the application's context. The tool
does not connect to a production service or a database to verify runtime state.

The telemetry is equally useful. In the default demo it records project context
as `DISABLED` and model review as `SKIPPED`. Only `Program.cs` is sampled initially;
the service file is not automatically reviewed in this mode. A finished report
therefore does not mean that every file has been inspected.

## 4. Try an actual model run

If Ollama is running locally and the example model is installed:

```sh
python scripts/demo.py --llm --model qwen3.5:9b --output demo-workspace-llm
```

The sample also contains a `PricingService.UnitPrice` method that divides by
quantity without a guard. The selector can request the omitted service file,
after which the audit and critic can examine it. Inspect the reported selected
files before deciding whether the model had enough evidence to identify the issue.

The original demo fixture labels its deliberate defect in a source comment.
This makes it an onboarding exercise, not a blind measure of bug detection.
The [paired evaluation cases](evaluation.md) keep their answer keys outside the
audited repositories and do not label defective implementations in source comments.

The optional demo asserts that the audit and critic completed. It does **not**
assert that their findings are correct. Check the actual report for a precise
location, a valid explanation, missed defects and unsupported findings.

## 5. Compare defective and corrected cases

Run the [evaluation starter](evaluation.md) when you want to compare a defective
implementation with its corrected counterpart. Keep all reports, including failed
or partial runs, and apply the manual rubric to the model findings.

Useful questions include:

- Was the relevant file actually included in the evidence?
- Does the finding describe the known defect accurately?
- Is the corrected counterpart still incorrectly reported as defective?
- Did the critic change the result, and did that change help?

The starter records execution evidence and deterministic expectations. Model
accuracy and the benefit of a critic require a separate assessment; neither is
inferred from a green test suite or a successful process exit.
