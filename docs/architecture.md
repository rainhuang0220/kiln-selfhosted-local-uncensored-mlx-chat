# Kiln — Local Qwen Chat Workbench

Technical selection and architecture for a ChatGPT-class web chat on top of
the local **Qwen3.8-27B AEON Ultimate Uncensored 4-bit MLX** checkpoint at
`../qwen3.8-27b`, served by **mlx-lm 0.31.3**.

This document is the contract. Implementation follows it.

---

## 1. Why this frontend?

**Choice: Vite 6 + React 19 + TypeScript (SPA).** Not Next.js, not Vue, not Svelte.

| Criterion | Decision |
|---|---|
| Product shape | Local-first workbench. No SEO, no multi-tenant SSR, no CDN HTML. |
| Backend already exists as BFF | FastAPI owns persistence, tokens, mlx. A Next.js App Router would duplicate that BFF. |
| Streaming | `fetch` + `ReadableStream` + `AbortController` is native. RSC adds ceremony. |
| Markdown / code | `react-markdown` + `remark-gfm` + highlight.js is the shortest production path. |
| Docker | Static `dist` behind nginx. Next.js would require a second Node process. |
| Occupied ports | This machine already has Vite on `:3000` and FastAPI on `:8000`. Kiln uses **5173** (web) and **8787** (API). |

Patterns copied from OSS (Open WebUI, LibreChat, Chatbot UI, LobeChat, AnythingLLM, FastChat):

- **Adopt:** three-pane ChatGPT layout (history / transcript / inspector); OpenAI-shaped messages (`role` + `content`); SSE token streaming; server-owned conversation ids; occupancy meter against a *practical* window.
- **Avoid:** Open WebUI / LibreChat / LobeChat as a fork (auth, multi-provider, Mongo, plugin marketplaces). FastChat Gradio (not a product UI). Dexie-as-source-of-truth (split-brain with SQLite).

Visual system: **Forge** — warm workshop, copper on bone, IBM Plex family, document transcript (not iMessage bubbles).

---

## 2. Why this backend?

**Choice: Python FastAPI + SQLite (WAL) + httpx.** Not Node, not talking to mlx from the browser.

1. Tokenizer lives next to the weights (`tokenizer.json`). Token accounting after the Qwen chat template is a Python job.
2. `mlx_lm.server` is OpenAI-compatible HTTP. The BFF is a thin orchestrator, not an inference engine. It must **not** import `mlx.core` or load 14 GB weights.
3. SQLite is enough for a single-user Mac app. WAL + one writer. No Postgres, no Mongo.
4. FastAPI SSE (`StreamingResponse`) maps cleanly onto mlx's `text/event-stream`.
5. A `ChatProvider` protocol keeps mlx as the first of N providers (later: tools/agents).

---

## 3. How we connect to mlx_lm.server

mlx-lm **0.31.3** (`/opt/homebrew/lib/python3.14/site-packages/mlx_lm/server.py`):

```
browser :5173  →  FastAPI :8787  →  mlx_lm.server :8081  →  qwen3.8-27b/
```

Host process (Metal, never Docker):

```bash
KMP_DUPLICATE_LIB_OK=TRUE mlx_lm.server \
  --model ../qwen3.8-27b \
  --host 127.0.0.1 \
  --port 8081 \
  --max-tokens 8192 \
  --temp 1.0 \
  --top-p 0.95 \
  --top-k 20 \
  --decode-concurrency 1 \
  --prompt-concurrency 1 \
  --prompt-cache-size 3 \
  --prompt-cache-bytes 1G \
  --prefill-step-size 512 \
  --chat-template-args '{"enable_thinking":true,"reasoning_effort":"medium"}'
```

Every BFF request:

- `POST http://127.0.0.1:8081/v1/chat/completions`
- Full `messages[]` every turn (server has no conversation store; LRU prefix cache matches token prefixes)
- `model: "default_model"` so mlx does not try to load another path
- `stream: true` and `stream_options.include_usage: true`
- `chat_template_kwargs: {enable_thinking, reasoning_effort, preserve_thinking}`
- Sampling from `generation_config.json`: temperature **1.0**, top_p **0.95**, top_k **20**
- Default `max_tokens=2048`, hard cap **8192** (27B on ~24 GB unified memory; 262,144 is theoretical only)

Field remap: mlx streams `delta.reasoning`; the Qwen jinja template reads `message.reasoning_content` on the next turn. The BFF stores `reasoning` as `reasoning_content`.

---

## 4. How conversations are saved

SQLite file `kiln/data/chat.db` is the **only** source of truth.

- `POST /chat` accepts **only the new user text** + optional `conversation_id`. The BFF loads history, truncates, calls mlx, persists.
- New conversation: mint UUID, insert system + user, generate, insert assistant + snapshot + generation_run.
- Continue: append user, same pipeline.
- Sidebar: `GET /conversation` ordered by `updated_at`.
- Delete: soft-delete (`deleted_at`) then hard-delete cascade from trash later. MVP: hard delete as requested by `DELETE /conversation/{id}`.
- The SPA is a view. No IndexedDB dual-write.

---

## 5. How context is displayed

After building the exact mlx payload, the BFF writes a `context_snapshots` row and emits it as SSE `event: snapshot` **before** tokens.

The inspector (right column / drawer) shows:

- Effective system prompt
- Exact `messages[]` posted to mlx (role chips)
- Truncation: dropped ids, policy
- Token table: prompt / completion / total / cached
- Occupancy bar against `PRACTICAL_PROMPT_BUDGET` (default 8192), footnote model max 262,144
- Generation params actually sent

The inspector is a debugger. If the BFF dropped turns or injected a thinking preamble, the transcript and the inspector **will disagree**. That is the feature.

Token counts: mlx `usage` when present; otherwise this checkpoint's HuggingFace tokenizer (`tokenizers` crate, local `tokenizer.json`). Never `len(text)//4`.

---

## 6. How memory extends later

Tables `memories`, `memory_evidence`, `embeddings` ship in v1 **empty**.

Rules locked now:

- Short-term memory = current conversation messages.
- Long-term memory = SQLite rows (`fact`, `preference`, `user_profile`, `episode`, `tool_result`).
- Memory is **untrusted retrieved data**, never merged into `role=system`. PromptBuilder injects a fenced block adjacent to the latest user turn.
- No auto-write of model-proposed memories. Accept / edit / delete comes first.
- Embeddings table reserved; sqlite-vec is a later migration, not a v1 dependency.
- RAG / user profile / agent memory plug into `MemoryService.retrieve()` without changing `/chat`.

See `docs/memory-layer.md`.

---

## 7. Process topology and ports

This machine already binds:

- `:8000` — unrelated FastAPI (`docxeditor`)
- `:3000` — unrelated Vite (`Flow`)
- `:8080` — Java

Kiln therefore uses:

| Process | Bind | Notes |
|---|---|---|
| Vite SPA | `127.0.0.1:5173` | proxies API paths to 8787 |
| FastAPI BFF | `127.0.0.1:8787` | never loads weights |
| mlx_lm.server | `127.0.0.1:8081` | Metal, host only |
| SQLite | `kiln/data/chat.db` | mode 0600 |

Loopback is the auth system. No `0.0.0.0`, no `CORS *`.

---

## 8. API surface

Product (SPA):

- `POST /chat` — create/continue, `stream=true|false`
- `GET /conversation` — list
- `GET /conversation/{id}` — transcript
- `GET /conversation/{id}/context` — last snapshot
- `GET /context` — global budget / defaults
- `DELETE /conversation/{id}`
- `PATCH /conversation/{id}` — rename
- `GET /health`

OpenAI-compatible (agents later):

- `POST /v1/chat/completions`
- `GET /v1/models`

---

## 9. Module boundaries

```
UI  →  API  →  ConversationService  →  ModelProvider  →  mlx_lm.server
                         ↘ MemoryService (stub)
                         ↘ PromptBuilder (truncate + fence)
                         ↘ SQLite repos
```

One in-flight generation globally. Second request → 409.

---

## 10. Defaults

| Knob | Value | Why |
|---|---|---|
| temperature | 1.0 | `generation_config.json` |
| top_p | 0.95 | same |
| top_k | 20 | same |
| max_tokens | 2048 (cap 8192) | 27B + thinking on 24 GB |
| enable_thinking | true | model card |
| reasoning_effort | medium | `xhigh` has no budget and can spend the whole cap inside `<think>` |
| preserve_thinking | false on history | prefix-cache + occupancy |
| practical window | 8192 | not 262,144 |
| overflow | truncate_oldest | keep system + latest user |

---

## 11. OSS survey (late report, folded in)

Surveyed: Open WebUI, LibreChat, Chatbot UI, LobeChat, AnythingLLM, FastChat Gradio.

**Confirmed (already shipping in Kiln):**

- Do not fork any of them (Open WebUI / LobeChat licenses; LibreChat Redis/agents; AnythingLLM pair-schema; FastChat Gradio).
- Browser never talks to mlx. FastAPI proxies OpenAI SSE.
- SQLite conversations + messages, not Mongo / Supabase / JSON blob.
- `stream_options.include_usage: true`; occupancy from server usage, not `len/4`.
- Isolate Qwen `reasoning` from `content`. Skip keepalive SSE comments.
- Always send `max_tokens` (mlx default 512 is unusable).
- Abort must persist `cancelled` + partial text (fixed after review).

**Deliberate divergence:**

- Product `/chat` uses **named events** (`meta`, `snapshot`, `delta`, `usage`, `done`) so the inspector can render the exact payload *before* the first token. `/v1/chat/completions` stays raw OpenAI SSE for agents.
- v1 history is **linear `seq`**, not `parentId` trees. Edit/regenerate-as-sibling is the next increment (Open WebUI / LibreChat pattern). Newest-first truncate already matches Chatbot UI `buildFinalMessages`.

**Explicitly deferred:** conversation tree, LLM auto-title, RAG workspaces, Socket.IO generation, Vercel `StreamingTextResponse`, Redis stream fabric.
