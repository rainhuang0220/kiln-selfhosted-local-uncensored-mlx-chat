# Kiln

**中文说明请看 [README.zh.md](README.zh.md)。**

Local-first, self-hosted chat workbench for **MLX models on Apple Silicon**.

Current release: **v0.6.6**.

```
browser :7777  →  FastAPI :8787  →  mlx_lm.server :8081  →  selected local model
```

## What you get

- Multi-turn chat with streaming and explicit terminal states (no silent truncation)
- Interactive Dialogue / Balanced / Reasoning profiles (dialogue defaults thinking off)
- Sidebar history (SQLite)
- Collapsible history, conversation delete, and message quote/delete
- Context inspector: exact payload sent to the model
- Token stats: TTFT, decode tok/s, effective output tok/s, occupancy
- Model Workbench: search Hugging Face in-app, inspect a repository, download an MLX-ready checkpoint, and select it locally
- OpenAI-compatible `POST /v1/chat/completions`
- Local Generate: image Fast (Z-Image Turbo Q4) and Quality (FLUX.1 [dev] Q4), Raw / Enhanced / experimental Translate+Enhance, plus short video (Wan2.1 1.3B). No application-layer filter; checkpoints are documented separately in [MODEL.md](MODEL.md). Do not read “uncensored” as “always follows the prompt.”
- Memory tables ready with account-scoped retrieval (no auto-write)

## Ports on this machine

Kiln uses **7777** (UI), **8787** (API), and **8081** (MLX inference). The verified default is Qwen3.5-9B Uncensored Aggressive in MLX mxfp4. Set `MODEL_PATH` before `npm run start:mlx` to use another compatible local model.

See [MODEL.md](MODEL.md) for the pinned 9B download, checksum verification, the local Model Workbench, and switching models. The former Qwen3.8-27B profile remains documented as a larger-model benchmark, not a runtime requirement.

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

# terminal B — persistent local API + UI (LaunchAgents; login keep-alive)
npm run start:local
```

Open http://127.0.0.1:7777

Optional public deployment is HTTPS static files plus an API-only reverse proxy. Do not expose the Vite development server. The maintainer instance is `https://kiln.plainlist.space`.

`npm run start:local` installs `com.kiln.api` and `com.kiln.web` without replacing the chat LaunchAgent `com.kiln.mlx`. For a foreground session instead, `bash scripts/dev.sh` or `npm run dev`.

## Tests

```bash
npm test
```

## Docker

`docker compose up --build` starts **API + nginx UI only**. `mlx_lm.server` must keep running on the Mac host (`npm run start:mlx`). Compose cannot put MLX inside Linux VM — there is no Metal there.

The local Compose profile mounts `MODEL_LIBRARY_HOST` at `/models`, so checkpoints remain outside Git and are visible to the API. One-click downloads and LaunchAgent switching run only in the native macOS setup above: a Linux container cannot control the host's Metal process. The Internet-facing Compose profile intentionally disables model management altogether; it is a read-only gateway to its separately managed inference host.

```bash
docker compose up --build
```

Then open http://127.0.0.1:7777. Set `MLX_BASE_URL=http://host.docker.internal:8081`.

## Authentication and public deployment

There are two modes.

**Local development (`KILN_EXPOSURE=local`)**  
Loopback only. The launcher sets this explicitly. Host headers never switch the app into private mode: a public or LAN Host in local mode is rejected. Unset `KILN_EXPOSURE` refuses startup.

**Private internet (`KILN_EXPOSURE=private`)**  
Auth is always required, including on localhost Hosts and with an empty users table. Set `COOKIE_SECURE=true` and `KILN_PUBLIC_ORIGIN=https://your.domain`. An empty users table is maintenance, not an open app. Create the owner on the Mac with `python -m app.cli create-owner`. Public signup stays off. Conversations, memories, and generations are owner-scoped. Model download/activate is owner-only.

Normal password change (knows the current password):

```bash
cd backend && ../.venv/bin/python -m app.cli change-password --username YOURNAME
```

Lost the current password but still have this Mac and the SQLite file:

```bash
cd backend && ../.venv/bin/python -m app.cli reset-password --username YOURNAME
```

Local recovery is filesystem/database admin access. There is no HTTP, email, or bootstrap-file reset.

Passwords are Argon2id. Browser sessions are opaque tokens stored as SHA-256 hashes. Default login is a browser session with idle and absolute timeouts. Check “在此设备保持登录” for a bounded persistent cookie.

Internet path:

```
HTTPS :443 → VPS nginx (web/dist + API routes)
           → 127.0.0.1:17777 (SSH reverse, loopback only)
           → Mac 127.0.0.1:8787 FastAPI
           → Mac 127.0.0.1:8081 MLX
```

Do not upload `chat.db` to the VPS. Do not publish 7777/8787/8081/17777. See [SECURITY.md](SECURITY.md).

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
| GET | `/health` | mlx reachability and chat park state |
| GET | `/generate/backends` | image/video backends and video presets |
| POST | `/generate` | enqueue a local image or video job |
| GET | `/models/local` | local model inventory (no paths) |
| GET | `/models/catalog` | live Hugging Face search |
| POST | `/models/download` | queue an MLX-ready local download |
| POST | `/models/{id}/activate` | select a downloaded model locally |

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
