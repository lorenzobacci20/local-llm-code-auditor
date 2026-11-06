# Optional scheduling

Set up a virtual environment, install the package, copy `agent.example.toml` to
`agent.toml` and select only repositories you are authorized to audit. Complete a
manual run first. Schedulers are optional; nothing is registered by installation.

## Windows

From the project directory in PowerShell:

```powershell
.\examples\register-task.ps1 -ProjectPath (Get-Location).Path -At "02:00" -Model "qwen3.5:9b"
```

The script registers a task for the current interactive user, pins the resolved
Ollama executable, ignores overlapping runs and invokes `scripts/run-nightly.ps1`.
The runner can start the local Ollama server and keeps logs for 30 days. It uses
static-only CLI mode; builds/tests remain disabled. Review the script before enabling
wake/battery behavior. Exit code 1 is recorded as findings, while invalid config or
repository selection remains an operational failure. Model failures also currently
use exit code 1: inspect report completion telemetry, not just Task Scheduler status.

Remove a task you registered with:

```powershell
Unregister-ScheduledTask -TaskName "Local LLM Code Auditor Nightly" -Confirm:$false
```

## macOS

`examples/local-llm-code-auditor.plist` is a template. Replace all absolute-path
placeholders, create the project `logs/` directory, select your desired schedule, and place a copy in your own LaunchAgents
directory. The template uses `--config` and relies on the configured repository roots.
It does not start Ollama; arrange for the local server to be available separately.
Logs and reports can contain sensitive metadata and model output. Keep them private.

The templates are supplied as optional integrations; no scheduler installation or
cross-platform runtime validation is claimed by the local test suite.
