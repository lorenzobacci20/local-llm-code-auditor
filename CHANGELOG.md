# Changelog

## 0.2.0 — release candidate

- Expand the paired synthetic dataset from six to 22 cases, including a multi-file selector task and clean controls. Keep executable probes and human rubrics outside model input.
- Capture the original audit draft and its own critic revision. Record inference metadata, time budgets, hashes and incomplete cases. Include an artifact-bound manual scoring workflow.
- Bound each model stage; limit selector choices to the paths shown. Record incomplete responses and fallbacks. Add strict-mode exit codes for unattended use.
- Write versioned JSON alongside Markdown, protect concurrent report writers and include a Markdown checksum. Treat model prose and indexed model claims as unverified.
- Add evidence redaction, loopback model validation, safer Git collection and link/junction checks. Exclude comments and string literals from the migration exception rule.
- Exercise wheel and source installations in fresh environments and audit resolved development/build dependencies in CI.

## 0.1.0

Initial public CLI with deterministic ASP.NET Core and EF Core analysis, source sampling, optional local selector/audit/critic, a synthetic demo and cross-platform CI. The subsequent evaluation starter added three defective/corrected pairs.
