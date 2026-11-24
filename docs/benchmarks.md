# Local evaluation · 24 November 2026

The deterministic suite completed **22 of 22 cases**. The expected four static rule instances appeared across two cases. Seventeen separate executable contract checks exercised C# pricing and Python behavior. These checks establish the synthetic ground truth and exercise the runner. They do not measure model accuracy.

The local inference experiment used only the public fixtures, disabled external context and skipped repository builds. It ran from clean software commit `ab280172ff91037bb78cf3a2296889cf38793f1a` against dataset v2, SHA-256 `f60265f40c97506c70c94280d50fc3c5b3d821573d48088c18da81469cb0a6ad`. Later candidate changes added a 2 MiB read limit for source/context files. The benchmark fixtures fit within it. See [run artifacts](benchmarks/) and [methodology](evaluation.md).

## What the captured replies show

| Case | Pipeline | Observable result |
| --- | --- | --- |
| c03, zero quantity | Qwen2.5-Coder 14B, paired audit + critic | The draft identifies the zero guard and division failure. The critic retains that finding and changes the verdict from GO to STOP. The executable contract observes `DivideByZeroException`. |
| c04, corrected guard | Same paired run | The audit reaches its 1,024-token output cap. No completed critic revision exists. An independent draft-only run completes. |
| c19, invoice threshold | Qwen2.5-Coder 14B, no selector vs selector | The initial three files omit `rounding.py`. The selector retrieves it and two other files. Even with that source present, neither the draft nor its own critic identifies the threshold defect. The public handler returns 100 where the contract requires 99. |

The c03 paired run took 60.38 seconds including setup and model load. Ollama reported 1,621 input and 108 output tokens for the audit at 29.74 generated tokens/s, then 1,257 input and 108 output tokens for the critic at 41.37 tokens/s. The c19 run with selector completed in 7.81 seconds. Model loading, cache state and different inputs limit timing comparisons.

These observations can be checked against the archived responses, contracts and independent tests. The per-finding human adjudications are pending. No precision, recall, F1 or comparative model ranking is reported.
