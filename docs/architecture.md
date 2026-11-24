# Architecture and output contract

The CLI resolves each target to a Git worktree. Git status, staged and unstaged diff, recent commit subjects, ASP.NET Core settings and EF Core artifacts provide evidence before a model is contacted. The static analyzers have no database connection. With `--run-build`, discovered .NET builds and tests can execute arbitrary repository-controlled code. Use that option only in an environment appropriate for the repository.

## Input budgets and model stages

1. The collector prioritizes changed files and samples across architectural roles. Source text, configuration-related evidence, Git text and optional external context pass through pattern-based redaction. The initial sample leaves room for follow-up reads when selection is enabled.
2. The selector receives bounded evidence and complete path records that fit its inventory budget. The parser checks returned names against the paths actually offered. Partial selector replies produce no follow-up reads.
3. Each request reserves room for output, the system prompt and framing. The final gate estimates three UTF-8 bytes per available token. Oversize evidence is shortened at both ends with an explicit omission marker. File counts describe collection; clipping can remove text from a collected file.
4. The draft and critic are sequential independent model calls. The critic receives the same bounded audit evidence and the full sanitized draft. If both cannot fit, the report retains the draft and marks the fallback. A completed critic can still miss a defect, erase a valid finding or add a false positive.
5. The CLI stages Markdown and JSON together, reserves a unique name and publishes the Markdown last. Concurrent runs on same-named repositories share a directory. Readers should discover `*.md` and use the sibling JSON with the same stem.

External context is opt-in. Set both `[context].enabled=true` and an explicit `path`. The loader accepts the root `AGENTS.md` and selected files in a matching project directory. Relative configuration paths resolve against the TOML file. Keep that directory and follow-up source within the same authorization scope as the audited repository.

Sampled source files and explicit context files larger than 2 MiB are omitted as whole inputs before redaction. Git output, inventories, .NET analyzer inputs and trusted builds have different resource costs. Prompt limits do not impose a global bound on collection I/O, process memory or the size of a repository. Use an isolated checkout and OS resource controls when those limits matter.

## JSON schema version 1

| Field | Meaning |
| --- | --- |
| `head`, `repository` | Audited repository’s Git identifier and directory name. A dirty worktree can differ from its commit. |
| `pipeline` | Selector, audit, critic and chosen final source. `NONE` indicates the absence of a model draft. |
| `stages` | Completion status, budget clipping and Ollama token counts, generation rate and duration when available. A null value means unavailable. |
| `files`, `followup_files`, `selector_paths_offered` | Sampled repository-relative paths, additional reads and inventory size sent to the selector. |
| `findings` | Static rule ID, analyzer, severity, file and evidence; model bullets matching the documented field order receive a content-derived ID and unverified status. Location, consequence or recommendation can be null. Multiple rule instances may share a rule ID. |
| `analysis` | Entire sanitized selected model response, including prose the structured index could not parse. Inspect this during adjudication. |
| `draft`, `revision` | Present with `--capture-draft`. A null revision means there was no completed critic. |
| `markdown_sha256` | SHA-256 over the sibling Markdown file’s bytes. This detects a mismatched pair; an author able to change both can recompute it. |

Model text is displayed literally inside a fenced block. Markdown links or HTML it contains are inert in standard Markdown renderers. Files and model results may still contain confidential information. Keep raw reports private by default.

## Exit codes

| Code | Interpretation |
| --- | --- |
| 0 | Deterministic checks completed with no high finding or failed build/test. Default mode permits selector/critic fallback. |
| 1 | High deterministic finding, build/test failure, or failed/partial main audit in default mode. |
| 2 | Invalid configuration, repository selection or Git snapshot. |
| 3 | Report-write failure, or a requested model stage failed, was partial or exhausted its budget under `--strict-pipeline`. |

Multiple repositories return the highest observed code. Static mode is explicit with `--no-llm`. A model verdict never sets the exit code. The Windows nightly wrapper opts into strict mode to distinguish incomplete model work from findings.
