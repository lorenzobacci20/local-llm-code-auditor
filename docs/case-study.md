# Building an evidence-first local code reviewer

A passing build could tell a reviewer that a pricing service compiled. It could not explain what would happen when a caller supplied zero as the quantity. The design question for Local LLM Code Auditor was how to put that code in front of a local model while preserving a record of what the reviewer could independently verify.

## Start with evidence that survives a model change

The CLI collects Git changes, checks ASP.NET Core configuration and inventories static EF Core migration artifacts. Each rule includes a repository-relative path and an explanation. These findings survive an unavailable model. The [public example](example-report.md) shows three configuration observations anyone can reproduce with Python and Git.

## Spend the context window on relevant code

Changed files and architectural roles guide the first source sample. A selector can request more files from an explicit inventory. The controller owns path validation, reading and byte limits. A partial selector response cannot authorize a follow-up. The report records which files were sampled, which were requested subsequently, and where input was clipped.

Local inference reduces where authorized code needs to travel, while the contents of a repository remain untrusted. Pattern-based redaction, a loopback transport, explicit model checks and opt-in build execution establish different boundaries. In particular, executing a project’s build is a separate trust decision from reading its sources. The model has no command executor.

## Make the critic’s contribution observable

Two independent drafts can differ even with the same settings. Comparing the final outputs of two runs would confound that variation with the change introduced by a critic. The paired mode keeps one draft, sends it to the critic with the same evidence, and records both replies. A failed critic leaves a visible gap in the pair. The evaluation guide defines a human review procedure for supported, missed and ambiguous claims.

## Engineering trade-offs

One measured run shows both the value and the limit of selection. On the invoice fixture, the first three files omitted the pricing rule. The selector then requested `rounding.py`. With that file in the prompt, both the audit and its critic still missed the boundary error. A separate executable test called the public handler with `[100]` and observed 100 against a contractual total of 99. That record distinguishes a successful file read from a failed semantic review. [Captured run](benchmarks/coder-selector/manifest.json)

A standard-library CLI keeps deployment small and makes offline deterministic checks straightforward. A byte-based budget can only approximate token usage. Static checks cover a narrow set of rules, and a second pass costs inference time without guaranteeing better findings. Publishing the contracts, input hashes, report format and negative results gives another engineer a way to examine those decisions.

[Actual benchmark results](benchmarks.md) · [Evaluation methodology](evaluation.md) · [Implementation and tests](../src/local_llm_code_auditor)
