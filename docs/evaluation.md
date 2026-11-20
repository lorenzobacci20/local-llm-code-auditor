# Synthetic evaluation starter

This small dataset separates three questions:

1. Did the implemented deterministic rules report the expected rule IDs?
2. Did the requested audit pipeline complete, including the critic when enabled?
3. Did the model identify a supported defect and avoid unsupported findings?

The runner checks the first two. **LLM finding quality is always `NOT_EVALUATED` in
its manifest.** A successful run, model verdict or matching word in a report is
not a quality score. The third question requires the manual rubric below.

## Run offline first

From a development installation of this repository:

```sh
python scripts/evaluate.py --help
python scripts/evaluate.py --list
python scripts/evaluate.py --output evaluation-runs/deterministic
```

The default runs all six cases through the actual CLI with `--no-llm` and
`--skip-build`. It requires Python and Git, but no Ollama, model, .NET SDK or
database. Use `--case c03` to select one case; repeat the option for a subset.

`--output` must name a new directory. An existing directory is rejected without
overwriting its contents. Every case gets an independent workspace and report
directory, avoiding collisions between reports from repositories with the same
name or runs within the same second.

## Dataset and ground truth

| Pair | Cases | Behavior under review | Deterministic oracle |
| --- | --- | --- | --- |
| Production settings | `c01`, `c02` | Detailed errors, loopback API address and Debug logging, followed by their corrected settings | Three ASP.NET rule IDs in `c01`; none in `c02` |
| Per-item price | `c03`, `c04` | Quantity zero passes a `< 0` guard before division; the corrected guard rejects `<= 0` | No implemented static rule for either case |
| Quantity discount | `c05`, `c06` | A documented ten-item threshold is implemented with `> 10`; the correction uses `>= 10` | No implemented static rule for either case |

The complete expected behavior and manual rubric live in
[`examples/evaluation/cases.json`](../examples/evaluation/cases.json). The common
project plus one case overlay form each target. Source comments describe its
business contract; they do not announce which implementation is defective.

The runner audits a new neutral temporary path such as
`auditor-eval-<random>/sample-app`, with branch `main` and commit message
`Sample project`. Case IDs, pair labels, answers, rubric and the user-selected
output path are excluded from that target. External project context is explicitly
disabled. Only after the audit does the runner copy the workspace into the output.

These are tiny fixtures, with two source files each. `max_files=16` makes both
available to the initial source sample under the default budget. Consequently the
selector normally reports `SKIPPED_NO_REMAINING_FILES`. This starter does **not**
evaluate selection quality on larger repositories. Custom low token budgets can
still truncate evidence; inspect each report's source coverage and truncation.

The examples are inspected statically: the runner neither builds nor executes the
C# application. The semantic expectations are documented contracts and manually
checkable examples, not claims that an application test suite was run.

## Optional local-model runs

Install and start Ollama and obtain the model separately. Then run:

```sh
python scripts/evaluate.py --llm --model qwen3.5:9b --thinking off --critic on --output evaluation-runs/critic-on
python scripts/evaluate.py --llm --model qwen3.5:9b --thinking off --critic off --output evaluation-runs/critic-off
```

Both commands use the existing local-only Ollama transport. `--thinking auto`
omits the thinking toggle for models that do not support it. Context and output
limits default to `--num-ctx 16384 --num-predict 4096`; the exact TOML and requested
settings are saved. A model tag does not identify immutable weights: record the
actual Ollama model digest, Ollama version and hardware separately when sharing
results. No real-model result is shipped or claimed by this starter.

`--timeout 300` is a **total subprocess time budget per case**, covering Git setup
and the whole CLI process, not 300 seconds per model request. The client process
is terminated on timeout; that does not guarantee immediate cancellation inside
the separate Ollama server. Remaining cases still run and the failure is recorded.

With the critic enabled, an audit or critic error, partial output or selector
fallback is incomplete even when the underlying CLI exits zero. With `--critic
off`, a completed audit and explicitly disabled critic are expected. The runner
does not attempt to judge the content of either answer.

## Artifacts and interpretation

The output contains:

- `manifest.json`: settings, dataset/package version, runner and input-file hashes,
  elapsed time, original CLI exit status, parsed pipeline telemetry, deterministic
  rule comparison and errors, updated after each case.
- `ground-truth.json`: the selected answers and rubric, outside all target repos.
- `c01/` through `c06/`: copied synthetic Git repository, exact `audit.toml`, complete
  original report when one was produced, and CLI stdout/stderr logs. Report paths
  inside the manifest are relative to the output directory.

Reports retain their original neutral temporary repository path for fidelity.
That temporary path no longer exists after the run; its saved copy is
`<output>/<case>/sample-app`. Reports are not normalized or abbreviated.

`deterministic_oracle.status=PASS` means the exact list of tool-generated rule IDs
matches the fixture expectations. It says nothing about LLM quality. In particular,
`c03` and `c05` intentionally pass that comparison with **zero deterministic
findings despite their semantic defects**. The parser reads only the deterministic
section before the model's repository analysis; model prose cannot add a scored
rule.

Case states are `COMPLETE`, `INCOMPLETE`, `ORACLE_MISMATCH`, `TIMEOUT` or `ERROR`.
`COMPLETE` means expected execution telemetry and deterministic rule IDs were
observed. An unavailable Git executable, missing/malformed report, nonzero CLI exit
or model failure cannot become a complete run. The runner returns `0` only when
all selected cases are complete, `1` for a case failure and `2` for invalid command
arguments or an unavailable output destination. These are runner exit semantics,
not new semantics for the auditor CLI itself.

## Manual model review

For each report, check whether both source files were actually supplied, then use
the corresponding rubric to record:

- **Supported finding:** the answer identifies a concrete defective condition,
  relevant file and consequence supported by the supplied evidence.
- **Missed seeded defect:** the designated defect is absent or described only as
  generic advice. Record missing/truncated evidence separately from reasoning errors.
- **Unsupported finding:** the claim contradicts a supplied guard or contract, or
  requires evidence the model did not receive. Count corrected counterparts as
  opportunities to identify these false alarms, not as universally defect-free code.
- **Unresolved finding:** a possible additional issue needs separate review; do not
  automatically label every issue beyond the seeded defect false.

Compare critic-on and critic-off reports using the same model, parameters and
input-file hashes, and repeat runs when investigating variability. These are
separate model calls: their initial drafts can differ. The current CLI retains only
the final report, so this comparison does **not** isolate the critic's causal effect
on the exact same draft. A paired draft-level experiment is future work.

Six cases are a regression/evaluation starting point, not a representative benchmark.
Do not turn their completion rate into accuracy, security coverage or a claim that
the critic improves review quality.
