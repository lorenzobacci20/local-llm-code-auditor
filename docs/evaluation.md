# Evaluating a local audit

The dataset contains 22 public synthetic cases with stated contracts. Six original
cases keep their identifiers. The runner sends a neutral Git repository to the
real CLI for each case. It verifies execution and deterministic rule IDs. A human
reviews the content of each model response before any quality metric is available.

## Run the deterministic suite

Use a development installation from the checkout. The evaluation scripts and
fixtures also ship in the source distribution.

```sh
python -m pip install -e ".[dev]"
python scripts/evaluate.py --list
python scripts/evaluate.py --output evaluation-runs/offline
python -m pytest -q tests/test_evaluation_contracts.py
```

Each audit skips builds. The independent tests run trusted, bundled Python
fixtures and compile four small C# pricing probes when a .NET 8+ SDK is available.
The C# probe restores against installed SDK reference packs with NuGet package
sources cleared. Pytest records a skip when a suitable SDK is absent. The
reservation probe advances two coroutines at a fixed suspension point to reproduce a specific
ordering without depending on sleeps.

| IDs | Contract under review |
| --- | --- |
| c01–c02 | Production ASP.NET settings cover detailed errors, default logging and a non-loopback API endpoint. |
| c03–c04 | A zero quantity must be rejected before decimal division. |
| c05–c06 | Quantity ten qualifies for the volume discount. |
| c07–c08 | The EF Core migration rollback must remove the column created by its forward change. |
| c09–c10 | A missing label receives a fallback before stripping whitespace. |
| c11–c12 | A malformed shipment quantity is skipped by the importer. |
| c13–c14 | A second reservation observes the stock held by a suspended first caller. |
| c15–c16 | Rejecting a batch preserves the opening balance. |
| c17–c18 | An owned output stream is closed even when writing fails. |
| c19–c20 | An invoice credit includes the threshold; the delegated implementation lives outside the first three source files. |
| c21, c22 | Clean controls exercise approval-role normalization and empty-window averages. |

In each pair the odd-numbered case carries the seeded defect. c01 has three
separate risks. Each case specifies its affected files, contract, observable
consequences, zero or more named defects, deterministic rule expectations and a
semantic review rubric. A clean case means the named contract holds for its
specified behavior. The fixtures support code-review experiments across languages.
Dedicated static rule analyzers cover ASP.NET and EF Core.

The runner creates a new temporary repository named `sample-app`, disables
external context, copies an optional source layout plus one overlay and makes
a synthetic commit with a fixed message and identity. The model sees ordinary
source comments describing public behavior. Case IDs, pairs, independent tests,
rubrics and expected defects stay outside the audit target. In c19/c20 the
six-file invoice workflow exposes `invoice_service.py` in its first three files.
It imports `rounding.py`. Only a follow-up read exposes the credit implementation.
`selector_target_read` records that observation separately from completion.

## Local model and paired critic

Select an installed local tag from `ollama list`. These commands use a shell
variable named `MODEL` containing that tag. In PowerShell assign
`$MODEL = 'your-installed-tag'` first.

```sh
python scripts/evaluate.py --llm --model "$MODEL" --case c05 --selector off --critic off --timeout 180 --suite-timeout 240 --num-ctx 8192 --num-predict 768 --output evaluation-runs/audit
python scripts/evaluate.py --llm --model "$MODEL" --case c05 --selector off --paired --timeout 240 --suite-timeout 300 --num-ctx 8192 --num-predict 768 --output evaluation-runs/paired
python scripts/evaluate.py --llm --model "$MODEL" --case c19 --selector on --paired --timeout 300 --suite-timeout 360 --num-ctx 8192 --num-predict 768 --output evaluation-runs/selector
```

The paired command captures the **one audit response actually supplied to its
critic** and the completed revision in the same JSON report. Inspect the two
strings and their SHA-256 hashes. A separate critic-off run measures a standalone
configuration. Only the within-run pair controls the initial draft. Use the same
model, tag digest, budgets and evidence selection when comparing configurations.
For a selector ablation, repeat c19 with `--selector off` while holding all other
options fixed. A selector can legitimately return an empty array. This loses the
target dependency on c19/c20 and is recorded even if all model calls completed.

The runner defaults to 300 seconds per case and 1,800 seconds for all case
subprocesses combined. Git setup and every stage share those remaining budgets.
Metadata reads use short timeouts. Unstarted cases retain `NOT_STARTED` after a
suite timeout. Copying artifacts and recording failures may extend wall time
slightly. Killing a client on timeout does not ensure the independent Ollama
server immediately stops computing. The output limit applies per model call.
`--thinking auto` omits the thinking flag when the selected tag requires that.

## Evidence and exit status

Use a fresh output directory per run. The manifest records the auditor version,
source-checkout commit and dirty flag when attributable, package source hash,
runner SHA, settings, dataset version/hash, time, pipeline status, source files,
stage token counts/rate/duration when reported, and post-case model allocation
when the local Ollama process still lists the tag. A null memory sample means
unavailable. This sample is an allocation snapshot, not peak process RAM.
Version and digest are requested from the loopback Ollama server without pulling
weights. The dataset digest hashes a sorted mapping of relative paths to SHA-256
for canonical LF text across the source layouts, case overlays and answer file.
Per-case input hashes cover actual file bytes in that workspace.

Each case directory retains the original Markdown and JSON report, copied synthetic
Git repository, exact TOML and stdout/stderr. These local artifacts can contain
host paths. Inspect and sanitize exports before sharing. A paired report also
contains model-generated text in its JSON. The JSON links the exact Markdown
bytes through a SHA-256 checksum. The runner checks both the checksum and
agreement of the deterministic rules and pipeline telemetry.

`COMPLETE` requires the expected tool exit code, deterministic rules and requested
pipeline. c07 expects CLI exit 1 because the planted HIGH rule fires. A missing
dependency, malformed report, timeout, unexpected exit, rule mismatch, required
stage fallback or partial response remains visible as an error or incomplete case.
The suite returns 0 only when all selected cases complete, 1 for case failures
and 2 for invalid command arguments. A successful deterministic run supplies no
measurement of model quality. In particular, semantic-only defects can produce
zero static rule IDs.

## Human adjudication

1. Keep the original run directory. Open the captured draft and revision (or
   final analysis only), verify the collected files and review the selected case's
   contract and independent test. Ideally have a second reviewer resolve
   disagreements without seeing which stage produced each answer.
2. In `judgments.json`, annotate every distinct actionable claim. Collapse repeated
   statements of the same defect. Exclude healthy telemetry, verdicts and generic
   suggestions that make no claim. For each entry record an exact `quote`, a
   `reason` grounded in a file and observable consequence, and a classification.
   Use `seeded` with the matching `defect_id`, `unsupported` for a contradicted
   or fabricated claim, `supported_additional` for independently confirmed
   unseeded defects, or `ambiguous` where the evidence is insufficient. A defect
   missed through missing/truncated evidence still counts as missed. Explain the
   coverage limitation in `notes`.
3. Fill `missed_defects` with seeded IDs without a supported match. When the entire
   artifact has been reviewed, set `status` to `verified` and supply the human
   reviewer's name or pseudonym. Preserve empty lists for genuinely empty cases.
   This attestation is a review workflow, not a digital signature.
4. Run `python scripts/score_evaluation.py evaluation-runs/paired`. It binds
   reviews to response digests, requires every completed response to be judged,
   rejects double matching and verifies the partition of seeded defects. Incomplete
   runs remain counted separately. Do not fill the records from an LLM verdict.

A finding entry could use this shape (replace all four values from the actual
reviewed response and contract):

```json
{"classification":"seeded","defect_id":"c05.1","quote":"exact response excerpt","reason":"file, condition and observed consequence"}
```

The score is **micro-averaged per stage across completed, manually reviewed
cases**. A supported match to a named seed contributes one TP. Each unique
unsupported finding contributes one FP. Every missed seed contributes one FN.
Verified additional and ambiguous findings are counted separately and excluded
from these seeded-task ratios. Precision is TP/(TP+FP), recall is TP/(TP+FN)
and F1 is 2TP/(2TP+FP+FN). A zero denominator is reported as null. Always report
counts, completion rate and exclusions next to ratios. The dataset is small and
purpose-built; repeated runs and blind human review help characterize variance.

The model receives the deterministic analyzer output. In c01 and c07 it can
repeat a rule that the tool already reported. Report these rule-backed pairs
(c01/c02 and c07/c08) separately when discussing independent semantic reasoning.
For a semantic-only run, select the other cases with repeated `--case` options
so its manifest and human judgments preserve that denominator.

[Full case contracts and rubrics](../examples/evaluation/cases.json)
