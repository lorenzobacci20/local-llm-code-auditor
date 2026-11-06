# Security policy

This is an early-stage local auditing tool. Security fixes target the latest release.
Do not attach secrets, private source code or unredacted reports to public issues.
Use the repository's GitHub **Security → Report a vulnerability** feature for a
private report when enabled; otherwise open a minimal issue requesting a private
contact channel without disclosing exploit details or sensitive data.

Include the version, OS/Python version, minimal synthetic reproducer and impact.
No response-time or vulnerability-discovery guarantee is offered.

The CLI is not an OS sandbox. The model receives unredacted local evidence and may
reproduce sensitive values despite instructions. Reports must be reviewed before
sharing. Builds/tests require `--run-build` and execute repository-controlled code.
See the README for transport, context, sampling and database-state limitations.
