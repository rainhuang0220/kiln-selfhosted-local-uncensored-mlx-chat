# Runtime comparison — M4 24GB, Qwen 27B 4-bit

This machine today:

| Tool | Installed | Notes |
|---|---|---|
| MLX-LM 0.31.3 | yes (Python 3.12 venv) | serving `qwen3.8-27b` 4-bit MLX on `:8081` |
| MTPLX 2.9.1 | yes (`models/.mtplx-venv`) | 4B/9B MTP on `:8082` (`npm run start:mtplx`) |
| llama.cpp / llama-server | no | would need GGUF conversion |
| Ollama | no | |
| LM Studio | no | |

## Table (honest)

| Framework | Decode | TTFT | Memory | Context | Streaming |
| --------- | -----: | ---: | -----: | ------: | --------- |
| MLX-LM 27B | **6.63 tok/s** decode; 62 prefill @1k | 2.7s cold / 0.74s cached | 14.1 GB weights | practical 8k | SSE OpenAI |
| MTPLX 9B | **24.2 tok/s**; 171 prefill | ~0.77s | 8.1 GB | native MTP | SSE `:8082` |
| MTPLX 4B | **52.1 tok/s**; 327 prefill | ~0.41s | 2.4 GB | native MTP | SSE `:8082` |
| llama.cpp | not measured | — | — | — | — |
| Ollama    | not installed | — | — | — | — |
| LM Studio | not installed | — | — | — | — |

**Decision:** keep MLX-LM for this uncensored 27B (decode stays ~6.6). ≥30 tok/s on this M4 24GB is the 4B MTPLX path, not a GGUF of the same 27B.

To revisit: convert to GGUF, install `llama-server`, run `benchmarks/run_inference.py` against an OpenAI-compatible port and append a row.
