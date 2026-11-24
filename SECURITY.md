# Security policy

## Reporting a concern

Security fixes target the current release. Use GitHub's **Security → Report a vulnerability**
when enabled. If it is unavailable, open an issue requesting a private contact channel.
Include the version, operating system, Python version, impact and a minimal synthetic
example in the private report. Keep credentials, private source and raw reports off
public issues.

## What reaches the model

By default the auditor inspects a local Git working tree, recent commit subjects,
staged and unstaged diffs, selected source files and static analyzer summaries.
`--no-llm` runs the deterministic path. External Markdown context requires an
explicit configuration path. An optional trusted build adds command output.

The collector masks recognizable credential-bearing lines before shortening source,
diffs, build output and context. The transport checks the assembled user message
and returned model text again. Covered patterns include common password, token,
API key and connection-string assignments, authorization headers, URI userinfo,
several provider token formats and delimited private key blocks. Removing a full
line can also remove useful evidence. Unlabelled or encoded secrets, unusual
formats, fragments without a key marker, proprietary business logic, personal data
and private names can survive. Authorize access to the original repository before
running the tool. Treat both Markdown and JSON reports, including saved drafts, as
confidential and inspect them before sharing.

## Local inference

The client restricts HTTP(S) requests to a loopback origin, disables proxies and
rejects redirects. Before each chat request, it queries `/api/show` with the model
name alone. Cloud tags, models advertising `remote_host` or `remote_model`, and
responses without local model format information are rejected. Use a trusted
Ollama process with stable model tags on the same machine. A malicious local
service, tunnel, changing model alias or incorrect server metadata can defeat
client-side checks. For an offline deployment set `OLLAMA_NO_CLOUD=1` on the
**daemon**, restart it and enforce egress restrictions appropriate to the data.
[Ollama local-only configuration](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features)

## Reads, commands and report access

Source selection uses a repository-derived file inventory. The collector rechecks
candidate paths before reading, rejects symbolic links and Windows reparse points,
and limits follow-up reads to allowed paths. Use a stable working tree under
operator control during the audit. Concurrent adversarial file replacement falls
outside this boundary. Use a dedicated clone and OS isolation for untrusted inputs.

Repository content and model responses can contain instructions designed to sway
a verdict. Selector replies can request paths from the offered inventory. The audit
and critic return text for review. The model has no shell, patch, push, deployment
or database command interface. Inspect every recommendation against the code.

The CLI invokes fixed Git argument lists and disables external diff, text conversion
and filesystem monitors on its snapshot path. Trust the Git executable, local Git
configuration, installed filters, environment and machine account. `--run-build`
allows the .NET toolchain to execute repository-controlled build logic and tests
with that account's permissions, including filesystem and network access. Use it
only on trusted code or in an isolated build environment without sensitive data.
Keep reports in an operator-owned directory outside the target repository and
restrict access using the operating system's file permissions. The scanner handles
evidence in process memory and has no encrypted storage or automatic retention policy.
