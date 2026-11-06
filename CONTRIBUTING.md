# Contributing

Use Python 3.11+ and a virtual environment, then `python -m pip install -e '.[dev]'`.
Run pytest, Ruff checks/format, the build and `python scripts/demo.py` before a PR.
Keep regression fixtures synthetic and use reserved example domains. Do not commit
local config, reports, logs, database dumps, credentials or private project details.

Changes to analyzers should include a focused regression test proving the finding
and counter-evidence. Preserve the boundary between deterministic evidence and model
interpretation. Never introduce model-generated command execution or automatic
source-control/database/deployment actions. Discuss additional dependencies and
changes to data sent to the local model explicitly in the PR.
