# Release validation

Validation date: **2026-11-06**. Local environment: macOS arm64, Git 2.50.1,
CPython 3.11.18 and 3.13.18. No private repository or credential is needed to run the tests.

| Check | Observed result |
| --- | --- |
| Isolated development installation, Python 3.11 | Passed; 67 pytest tests passed, zero skipped |
| Isolated development installation, Python 3.13 | Passed; 67 pytest tests passed, zero skipped |
| `ruff check .` and `ruff format --check .` | Passed |
| `python -m build --no-isolation` | Wheel and source distribution built |
| Wheel installed in a separate environment, no dependencies | CLI help and deterministic demo passed |
| `python scripts/demo.py` | Three expected synthetic ASP.NET findings, LLM explicitly skipped |
| Real synthetic .NET build and CLI `--run-build --no-llm` | Passed with SDK 10.0.300 targeting net8.0, zero build warnings/errors; test execution correctly skipped because this fixture has no test projects |
| `pip-audit --skip-editable` | No known vulnerabilities in the audited development environment (37 entries); runtime dependencies are empty |
| `actionlint .github/workflows/ci.yml` | Passed |
| `bash -n scripts/install-macos.sh`, `plutil -lint` on launchd template | Passed |
| Gitleaks 8.30.1, exported working tree and independent one-commit history | No leaks detected |
| Clean local clone: isolated install, tests, lint/format, CLI, demo and isolated build | Passed; 67 tests passed |
| Real Ollama synthetic demo, qwen3.5:9b | Passed with explicit think=false, 16,384 context and 4,096 output-token limit: selector, audit and critic COMPLETE; final report source CRITIC; smoke command exited 0. |

## Interpretation

The deterministic demo and tests use synthetic fixtures. Mocked model responses test
orchestration/fallbacks; they are not evidence of model accuracy. The real-model
smoke check completed on the synthetic repository. An earlier run using model-default
thinking exhausted the critic output budget and correctly fell back to the draft.
An explicit thinking toggle was added, tested and used to obtain the complete run.
No recall, precision, throughput
benchmark or comparative critic improvement is claimed.

The optional Windows scheduler has not been installed during this validation, nor
has the macOS launchd template. [GitHub Actions run 42300694713](https://github.com/lorenzobacci20/local-llm-code-auditor/actions/runs/42300694713)
passed for application commit `c32eccb3bbe56e8e44c27f893ed0272234e9c6f7`: all six
Linux/macOS/Windows × Python 3.11/3.13 jobs and the Gitleaks history/tree job succeeded.
The current commit status is available from the repository Actions tab and README badge.

Gitleaks and manual review reduce publication risk but are not proof of absence of
all sensitive information. Generated reports remain private by default, and the
runtime model input has no universal secret-redaction layer. See the README and
SECURITY.md for the exact trust boundary and residual limitations.
