# Independent release review · v0.2.0

## 1. Release blockers

The independent review found no open blocker for submitting the candidate to the maintainer. It covers the local CLI, the release artifacts, and the published synthetic evaluation. The baseline was public main at `d2ae67f934eb7efeab45e4c6308d662997563819`. The reviewed source and evidence commit is `9f199b783d2001501869a26fa3baebfa1dd98895` on `codex/portfolio-v0.2.0`. No production installation or deployment forms part of this decision.

## 2. Near-term corrections

Five confirmed medium findings reached **VERIFIED** status. RULE-01 covers an EF false positive on comments and literals. EVAL-01 binds the answer key and scored output to the run manifest. TEST-01 restores execution of both invoice handler probes. OPS-01 bounds per-file source/context reads and documents the remaining collection costs. ART-01 preserves the exact bytes of the published example and measured reports. The targeted code regressions passed independently and the committed archive checksums matched. The individual observations and corrections are in the [review record](0.2.0-review.md).

## 3. Improvements

Human adjudication of each actionable finding would support a later quality study. Repeated trials with identical settings would characterize variation. The published quality judgments remain pending, and the evidence supports no precision, recall, F1 or model ranking.

## 4. Runtime checks and ownership

- **Maintainer.** Inspect the PR check suite on its final head after this report is added. Merge, tagging and package publication require a separate maintainer decision.
- **Operator.** Before using proprietary code, authorize the repository, trust the local Ollama daemon, restrict data access and select an appropriate environment for any opt-in build. Pattern-based redaction can miss sensitive content.
- **Benchmark reviewer.** The experiments used public fixtures from measured commit `ab280172ff91037bb78cf3a2296889cf38793f1a`. Reports record six complete and six incomplete case runs on three locally installed models. The candidate adds a read-size guard after the measurement commit. The synthetic files fit within it. Model-free regression checks cover the later code.

## 5. Regression checklist

| Scenario | Observed evidence |
| --- | --- |
| Install both candidate distributions outside the checkout | Each matrix job builds and installs the wheel and sdist in separate environments and exercises the deterministic demo. |
| Exercise all supported operating systems | Ubuntu, Windows and macOS each passed 127 tests on Python 3.11 and 3.13. |
| Run the deterministic suite and executable contracts | All 22 rule expectations matched. The fixture tests include 17 executable contract probes. |
| Preserve local-only boundaries | Transport, privacy, link handling and allowlisted follow-up regressions passed. Builds and external context were disabled in the published benchmarks. |
| Handle failed or partial model stages | Partial audits, skipped critics and completed pairs appear separately in the archived measurements. Strict-mode and fallback regressions passed. |
| Preserve report integrity and provenance | Independent verification from `git archive` matched the example and all 12 report/sidecar chains, selected ground truths and available response hashes. |
| Check the source and dependency supply chain | Both Gitleaks scans completed without a finding. The resolved dependency audit on Linux/Python 3.13 returned no known vulnerabilities. |
| Check portfolio claims against captured output | The 14B critic retained the zero-quantity finding on c03. The selector retrieved the omitted dependency on c19, but the final review still missed the threshold defect. |

## 6. Technical verdict

**GO for maintainer review of the v0.2.0 release candidate.** The FULL audit evaluated delivery, privacy and recoverability alongside functional behavior, report concurrency and evidence consistency. There is no hosted deployment, live database or graphical client to certify. The CLI can miss defects, generate unsupported findings and encounter model-specific limits. Aggregate memory and I/O still depend on Git, framework analyzers and optional builds.

The reviewer verified the checkout SHA in all seven job logs and the successful six-job matrix and secret scan on 24 November 2026. The macOS/Python 3.11 job completed at approximately 13:11 UTC. The technical verdict applies to the reviewed source and evidence commit above. The PR check suite remains the current source for subsequent commits. [GitHub Actions run 45399724135](https://github.com/lorenzobacci20/local-llm-code-auditor/actions/runs/45399724135) · [Pull request #2](https://github.com/lorenzobacci20/local-llm-code-auditor/pull/2)
