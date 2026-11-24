# Local model support

The CLI uses Ollama’s non-streaming chat API. It requires a local, installed chat model, an HTTP(S) loopback origin and model metadata that identifies local weights. The default configuration uses `qwen3.5:9b`. To choose another installed model, use its name exactly as reported by `ollama list`.

```sh
ollama list
ollama show MODEL
python scripts/demo.py --llm --model MODEL --thinking auto
```

The local client checks `/api/show` before sending evidence. It rejects cloud-marked tags, redirects, remote model metadata and unavailable metadata. The process still trusts the server at the selected origin. Use a trusted daemon with cloud features disabled. Model availability, license, effective context size and disk/RAM requirements depend on the actual weights and host.

The demo uses a 16,384-token requested context, a 4,096-token output limit and a 300-second per-request timeout. The evaluator can choose different limits and imposes its own per-case and suite deadlines. For models that reject a thinking toggle, use `--thinking auto` and omit `think` in a custom TOML file. A model can consume its output budget before producing a usable reply.

The draft and critic use separate requests to the same model and share the audit evidence. The selector is useful when its inventory contains files outside the initial sample. Inspect stage status, file coverage, prompt clipping and token telemetry together. [Measured configurations and negative results](benchmarks.md) · [Previous release validation](validation.md) · [Ollama chat API](https://docs.ollama.com/api/chat)
