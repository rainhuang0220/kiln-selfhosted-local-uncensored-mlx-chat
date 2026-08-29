# Kiln

**中文说明请看 [README.zh.md](README.zh.md)。**

Local ChatGPT-class workbench for **Qwen3.8-27B** on Apple Silicon.

Current release: **v0.2.4**.

```
browser :5173  →  FastAPI :8787  →  mlx_lm.server :8081  →  qwen3.8-27b/
```

## What you get

- Multi-turn chat with streaming
- Sidebar history (SQLite)
- Context inspector: exact payload sent to the model
- Token stats: input / output / total / occupancy
- OpenAI-compatible `POST /v1/chat/completions`
- Memory tables ready (retrieve stubbed; no auto-write)

## Ports on this machine

`:8000`, `:3000`, and `:8080` are already taken by other apps. Kiln uses **5173** (UI), **8787** (API), **8081** (mlx 27B, ~6.6 tok/s). Optional **8082** is MTPLX (`npm run start:mtplx`, 4B ~52 tok/s on this M4); point the API with `MLX_BASE_URL=http://127.0.0.1:8082`.

## Run

Needs: Node 20+, **Python 3.12** (not 3.14 — MLX + Homebrew OpenMP abort the 3.14 interpreter).

```bash
cd kiln
# one-time — pin 3.12
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python mlx mlx-lm -e "./backend[dev]"
npm install
npm install --prefix web

# terminal A — model server (Metal, not Docker)
npm run start:mlx

# terminal B — API + UI
npm run dev
```

Open http://127.0.0.1:5173

Or `bash scripts/dev.sh` for API+UI after the venv exists.

## Tests

```bash
npm test
```

## Docker

`docker compose up --build` starts **API + nginx UI only**. `mlx_lm.server` must keep running on the Mac host (`npm run start:mlx`). Compose cannot put MLX inside Linux VM — there is no Metal there.

```bash
docker compose up --build
```

Then open http://127.0.0.1:5173. Set `MLX_BASE_URL=http://host.docker.internal:8081`.

## Authentication and public deployment

Kiln's public mode uses individual accounts: passwords are stored only as Argon2id hashes, browser sessions are opaque random tokens stored as hashes in SQLite, and conversations are scoped to their owner. Configure the first account through `BOOTSTRAP_USERNAME` and `BOOTSTRAP_PASSWORD`; do not enable public signup unless you intend to run a self-service service.

For an Internet-facing deployment, copy `deploy/.env.example` to a private `deploy/.env`, set a DNS name and unique bootstrap password, then run:

```bash
docker compose -f deploy/compose.yml --env-file deploy/.env up -d --build
```

The Caddy ingress obtains and renews TLS certificates automatically. Public deployment requires `KILN_DOMAIN` to resolve to the host and ports 80/443 to be reachable. Do not expose the API port, copy database files, or commit `.env`, certificates, or runtime data.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/chat` | Product chat (`stream: true` SSE) |
| GET | `/conversation` | History list |
| GET | `/conversation/{id}` | Transcript |
| GET | `/conversation/{id}/context` | Last snapshot |
| GET | `/context` | Global budget |
| DELETE | `/conversation/{id}` | Hard delete |
| GET | `/memory` | Long-term memory (empty stub) |
| POST | `/v1/chat/completions` | OpenAI compatible |
| GET | `/health` | mlx reachability |

## Security

See [SECURITY.md](SECURITY.md) for the supported configuration, reporting guidance, and the boundary between publishable source and private runtime data.

## Docs

中文：

- [README.zh.md](README.zh.md) — 怎么跑、端口、速度
- [docs/架构.md](docs/架构.md)
- [docs/推理说明.md](docs/推理说明.md)
- [BENCHMARK.zh.md](BENCHMARK.zh.md)
- [docs/记忆层.md](docs/记忆层.md)
- [docs/框架对比.md](docs/框架对比.md)

English:

- `docs/architecture.md` — stack choices and mlx contract
- `docs/memory-layer.md` — short-term / long-term / RAG extension
- `docs/inference-mlx.md` — KV / prefix cache / speculative
- `BENCHMARK.md` — measured tok/s
