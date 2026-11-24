# Roadmap

The current CLI has language-independent Git collection and bounded source sampling. ASP.NET Core configuration and EF Core migrations have specialized, static rules. The benchmark includes Python contracts. A Python test runner, Node.js package-script discovery and dedicated analyzers for either language remain possible extensions.

| Next question | Evidence required before implementation |
| --- | --- |
| Does the critic improve supported findings? | Repeated same-draft comparisons with independent human adjudication, including corrections and regressions. |
| Does the selector surface relevant files? | Recall of required paths outside the first sample on more repositories, under a fixed budget. |
| Is a new language analyzer warranted? | A concrete rule with observable consequences, paired fixtures and regression coverage. |
| Would model-specific tokenization improve budgeting? | Recorded clipping or overflow attributable to the byte/token estimate. |

The tool's scope is read-only review with optional trusted builds. Language support can grow independently of deployment infrastructure.
