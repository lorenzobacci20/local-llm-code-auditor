# Release notes · v0.2.0 candidate

This candidate adds an inspectable comparison between a model draft and its own critic revision. A 22-case synthetic corpus covers deterministic .NET findings and semantic contracts in C# and Python. The CLI keeps the runtime dependency list empty.

### Compatibility

Existing configuration, the console entry point, `--no-llm`, opt-in builds and Markdown reports remain available. Recognized secrets are masked, model output renders as literal text and an absolute repository path is no longer included in a report. Consumers that parsed Markdown should migrate to the schema-v1 JSON sidecar. `--strict-pipeline` exposes incomplete requested stages as exit 3. The Windows nightly wrapper enables this mode.

A local Ollama service must support model metadata checks before receiving evidence. Unsupported metadata, a remote-backed model or a model request failure is visible in pipeline telemetry. Operators can still run the deterministic CLI without Ollama.

### Validate a checkout

```sh
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m build
python scripts/check_distributions.py
python scripts/demo.py --summary
python scripts/evaluate.py --output evaluation-runs/release
```

The distribution smoke test installs each artifact in its own temporary environment and invokes the CLI outside the project directory. To inspect a real model result, use the pinned software and dataset identifiers in the [benchmark record](benchmarks.md). For release gating, compare the PR head with the Actions run and inspect all six OS/Python jobs and both secret scans.

### Release decision

The maintainer reviews the candidate, the [independent audit](audit/results/12-final-go-live.md), and the checks on the current PR head before approving a merge or public release. The suggested tag is `v0.2.0`. A local distribution build, draft PR or successful CI run does not publish a package.
