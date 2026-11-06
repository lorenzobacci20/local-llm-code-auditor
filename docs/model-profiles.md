# Local model configuration

The CLI uses Ollama's [non-streaming chat API](https://docs.ollama.com/api/chat).
Install Ollama separately and choose a **locally downloaded** model appropriate for
available RAM/VRAM. The example configuration uses
[`qwen3.5:9b`](https://ollama.com/library/qwen3.5:9b); model weights are not included.
The model has its own license, independent of this repository's MIT license.

```sh
ollama pull qwen3.5:9b
local-llm-code-auditor --config agent.toml --repo /path/to/repository \
  --model qwen3.5:9b --num-ctx 16384 --num-predict 4096
```

A larger context increases memory use. Source sampling reserves output/headroom
using a character-to-token estimate; it is not a tokenizer-enforced context bound.
Large diffs, external context, the selector inventory and critic draft can still
exceed a model's effective context. Reduce evidence limits or increase context on
suitable hardware, and inspect truncation/completion telemetry.

For models supporting the Ollama thinking toggle, `[agent].think = false` disables
reasoning output; omit `think` for models without that capability. The synthetic
demo defaults to `--thinking off` and uses a 300-second timeout per request. Use
`--thinking auto` to leave the choice to the model, or `--thinking on` to enable it.

The selector and critic are additional sequential requests to the same local model.
They can improve an individual report but have no measured accuracy guarantee.
The critic falls back to the draft when unavailable or incomplete; telemetry makes
that fallback visible. Do not compare models from a single anecdotal report.

Check completion, useful supported findings, false positives and memory use on the
same synthetic input before using a model on real projects. No comparative model
benchmark is claimed. Cloud-backed Ollama model tags are outside the intended trust
boundary: configure Ollama for local-only use and do not select cloud models.
