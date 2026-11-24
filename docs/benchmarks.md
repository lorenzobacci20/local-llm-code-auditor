# Local evaluation · 24 November 2026

The deterministic suite completed **22 of 22 cases**. The expected four static rule instances appeared across two cases. Seventeen separate executable contract checks exercised C# pricing and Python behavior. These checks establish the synthetic ground truth and exercise the runner. They do not measure model accuracy.

The local inference experiment used only the public fixtures, disabled external context and skipped repository builds. It ran from clean software commit `ab280172ff91037bb78cf3a2296889cf38793f1a` against dataset v2, SHA-256 `f60265f40c97506c70c94280d50fc3c5b3d821573d48088c18da81469cb0a6ad`. Later candidate changes added a 2 MiB read limit for source/context files. The benchmark fixtures fit within it. See [run artifacts](benchmarks/) and [methodology](evaluation.md).

## Inference budget and outcomes

Ollama 0.40.18 ran on Windows with 20 logical CPUs, 63 GiB of OS-visible RAM and an RTX 5060 Ti. The wall-clock budget was 20 minutes. The experiment took 637 seconds from the first run through the last. It used three installed models. A small-model comparison would have required downloading other weights. No weights were downloaded.

There were **12 case/configuration observations on three distinct fixtures** across eight runs. Six completed their requested pipeline. Six reached the audit output limit and had no critic revision. The primary runs used a requested context of 8,192 tokens, temperature 0.1, model-default thinking and an output cap of 1,024 per request. The last two repeated c03 at 3,072 output tokens. Per-case and suite deadlines, model digests, individual file names, stage timings, input/output tokens and generation rates are in each manifest.

| Model and mode | Case IDs | Output cap | Complete / attempted | Record |
| --- | --- | ---: | ---: | --- |
| qwen2.5-coder:14b, draft only | c03, c04 | 1,024 | 2 / 2 | [Manifest](benchmarks/coder-draft/manifest.json) |
| qwen2.5-coder:14b, paired critic | c03, c04 | 1,024 | 1 / 2 | [Manifest](benchmarks/coder-paired/manifest.json) |
| qwen2.5-coder:14b, paired critic, selector disabled | c19 | 1,024 | 1 / 1 | [Manifest](benchmarks/coder-no-selector/manifest.json) |
| qwen2.5-coder:14b, selector + paired critic | c19 | 1,024 | 1 / 1 | [Manifest](benchmarks/coder-selector/manifest.json) |
| gpt-oss:20b, paired critic | c03, c04 | 1,024 | 0 / 2 | [Manifest](benchmarks/oss-paired/manifest.json) |
| qwen3.8:27b, paired critic | c03, c04 | 1,024 | 0 / 2 | [Manifest](benchmarks/qwen-paired/manifest.json) |
| qwen3.8:27b, paired critic | c03 | 3,072 | 1 / 1 | [Manifest](benchmarks/qwen-more-output/manifest.json) |
| gpt-oss:20b, paired critic | c03 | 3,072 | 0 / 1 | [Manifest](benchmarks/oss-more-output/manifest.json) |

The post-case Ollama snapshots reported roughly 10.4 GB loaded for the 14B model, 12.7 GB for the 20B model and 18.3 GB for the 27B model. These are model-residency observations. Peak host RAM was not measured. Reasoning tokens may count toward the reported output cap. [Deterministic results for all 22 cases](benchmarks/deterministic-summary.json)

## What the captured replies show

| Case | Pipeline | Observable result |
| --- | --- | --- |
| c03, zero quantity | Qwen2.5-Coder 14B, paired audit + critic | The draft identifies the zero guard and division failure. The critic retains that finding and changes the verdict from GO to STOP. The executable contract observes `DivideByZeroException`. |
| c04, corrected guard | Same paired run | The audit reaches its 1,024-token output cap. No completed critic revision exists. An independent draft-only run completes. |
| c19, invoice threshold | Qwen2.5-Coder 14B, no selector vs selector | The initial three files omit `rounding.py`. The selector retrieves it and two other files. Even with that source present, neither the draft nor its own critic identifies the threshold defect. The public handler returns 100 where the contract requires 99. |
| c03, zero quantity | Qwen 27B, 3,072 output tokens | The critic changes the exception type from `OverflowException` to the observed `DivideByZeroException`. It also asserts an expected HTTP 400 response that the fixture contract does not establish. The pair took 177.53 seconds. |

The c03 paired run took 60.38 seconds including setup and model load. Ollama reported 1,621 input and 108 output tokens for the audit at 29.74 generated tokens/s, then 1,257 input and 108 output tokens for the critic at 41.37 tokens/s. The c19 run with selector completed in 7.81 seconds. Model loading, cache state and different inputs limit timing comparisons.

These observations can be checked against the archived responses, contracts and independent tests. The per-finding human adjudications are pending. No precision, recall, F1 or comparative model ranking is reported.

To repeat the selector run after installing the checkout and verifying the model with `ollama list`:

```sh
python scripts/evaluate.py --case c19 --llm --model qwen2.5-coder:14b --thinking auto --selector on --critic on --paired --num-ctx 8192 --num-predict 1024 --timeout 125 --suite-timeout 150 --output evaluation-runs/repeat-c19
```

Use a fresh output directory each time. To repeat an exact recorded configuration, copy the corresponding manifest's case IDs, settings and deadlines. The preserved observations include incomplete outputs and pending judgment forms. Only the portable report pairs and scoring inputs are published.
