# Changelog

## Unreleased

- Context presets V21: each Studio character card is 名称 plus a one-sentence 身份, then 相关事件 n. The header starts collapsed; opening it lists every timeline event whose who[] names that person exactly, in timeline order, as wrapping text up to 500 characters. The one-line 一件事（可选） field is gone from Studio (`one_event` still loads from old presets). The public Studio payload now carries event summaries up to 500 characters instead of 100; stored presets and chat send still bound summaries at 100. The bottom 已绑定事件 list is unchanged.
- Context presets V20: school-year words in a long paste (小学三年级, 初二, 高一 …) are timeline cues, not a preview block. 「解析并预览」 no longer skips the 9B people extract or the alias resolver because of them, and Studio no longer shows 内容涉及未满十八岁的人物. Empty cards with 模型没有分析，请重试。没有使用规则名册。 mean only that the local model did not return people JSON. The binder still drops sexual timeline beats when the paste reads as under 18.
- Context presets V19: a long-paste 「解析并预览」 the 9B did not analyze fails visibly. No runner, busy chat, an extract error, or no people JSON returns empty characters and timeline with `extract.model_ran = false`, and Studio says 模型没有分析，请重试。没有使用规则名册。 The rules roster fallback is gone from this path, and so are the last-chance name scan and the rules identity/event backfill: grounding only drops a person or blanks a field. A successful preview carries `extract.mode = "model"`, `model_ran`, `elapsed_s`, `window_chars`, and Studio shows 模型已分析 · Ns. Short pastes stay rules-only (`rules_short`). Reference windows run one after another with a 75 s clock each and a 170 s total cap, because the local server decodes one request at a time and the second concurrent window used to time out in the queue. The nginx vhost gives `/context/presets/preview` a 180 s read timeout.
- Context presets V18: 「解析并预览」 on pastes of 800+ characters runs the 9B first. One people extract per 1200–1800-char reference window (200 overlap, live lock ≤200 chars, fixed compiler system prompt, thinking off, temperature 0, ≤1200 tokens), windows in parallel, 90 s cap. Rules run second and only keep, fold, or drop what the model returned: names must be verbatim and not aliases, identities must be attached to that name by the source (kinship by apposition only), and a job the source gave to someone else is dropped. The 36/30-char alias-clip resolve and the 220-char clipped fill no longer run on the preview path. If every window fails, the preview falls back to the V17 rules harvest minus the alias blocklist and says so. Chat send is unchanged.
- Context presets V17: pronouns, kinship words, and role nouns (他 / 她 / 姐姐 / 妈妈 / 宝宝 / 闺蜜 / 老师 / 队长 …) never become character rows, from rules harvest, the model fill, or the public Studio payload. 姐姐陆遥 / 姐姐是陆遥 / 陆遥是我姐姐 folds 姐姐 onto 陆遥 without a model, and alias mentions bind events to the named person. A proper name that appears once is kept when it sits on an identity anchor, or on a 说 / 问 anchor behind a common surname. 「解析并预览」 on pastes of 800+ characters runs one closed-set 9B alias resolve (live lock + candidate names + alias clips, 45 s cap) that also returns grounded short identities; the older clipped fill runs only when its full 50 s budget fits under the 60 s cap. Shorter pastes stay rules-only. Chat send is unchanged.
- Context presets V16: attention layers keep a short live parlor lock (L0) above long reference bibles; default hop omits confirmed_background and caps preference_bank to one ≤80-char hint. Shared-scene beats keep every co-actor in who[] (max 4); consecutive merge requires equal who-sets. New adult fixture `preset_shared_scene_ten` covers multi-name loft / library / awning nights. StyleBank fence is skipped when Context IR is bound.
- Context presets V15: binder attaches every Studio event to a harvested person (or drops it), merges consecutive same-who slices into story beats, and strips compiler IR / 待确认 / 文档分区 from the public Studio payload. Chat send stays rules-only; optional 9B binder runs only on 「解析并预览」.
- StyleBank same-hop intercept strips offstage names from the assistant bubble on the same `message_id` before finalize; singleton corpus names (no「X是她的某角色」frame) enter the bank once. Parenthetical 风格参考 is split and stored for every profile so Interactive / Balanced / Reasoning cannot dump the raw 2.5k corpus (compact `<style_bank>` fence stays immersive-only).
- Immersive loop-guard: short sensory clauses under 40 characters may recur; three consecutive full sentences still trip `hard_self_loop`. Guard-aborted hops that add fewer than 80 unique characters do not spend a useful auto-continue slot; total provider calls this turn are hard-capped at 6 when `auto_continue_max` is below 6. Immersive `auto_continue_max` is 5; below the 5000-char floor, stub_streak no longer stops Continue (sensory deepening often fails `beat_advanced`).
- Auto-continue after a guard trim no longer resends a prefix that mlx-lm already holds as a prompt-cache key. The turn's first chat-completions prompt counts as used, and a hop that follows a loop, run-on, stall, or fill-hop trim starts by dropping two tokens instead of one. Untrimmed Continues still drop one token. An exact cache hit had killed the mlx-lm generate thread and ended long Immersive turns in `timeout`.

## v0.7.0 — Immersive Dialogue defaults and long-output continuation

- Immersive Dialogue (沉浸对话) is the default profile for new chats: `max_tokens` 6144, thinking off, and auto-continue of the same assistant message (up to 3 hops, soft total cap 12288 completion tokens) until at least 5000 visible characters. Continuation triggers on `stop` as well as `length`. No application-layer content filter; uncensored behavior depends on the local checkpoint.
- The model dropdown shows two profiles: Immersive Dialogue and Fast Chat (短对话, formerly Interactive Dialogue, 3072 tokens, no auto-continue), each with a one-line explanation. Balanced is gone from the UI. `fast` / `conversational` alias Fast Chat; `long_form` / `narrative` / `multi_scenario` alias Immersive Dialogue and do not start the 20K narrative job (that still needs an explicit `mode=narrative`).
- Scene continuity: a deterministic extractor turns the current user turn plus the previous assistant turn into short keyword pins (names and forms of address, body marks, objects and their places, time agreements, locations). Pins are sent as `<must_keep>` / `<lore>` / `<scene_state>` blocks next to the latest user message, never in the frozen system prompt. The current user turn is never truncated.
- If an Immersive reply omits every mention of a pinned fact, Kiln appends one repair continuation (at most 512 tokens) to the same message.
- Auto-continue hops below the 5000-character floor suppress end-of-turn tokens and size `max_tokens` to land past the floor; a trailing half-sentence is trimmed when the floor still holds. If a reply starts by retyping the previous assistant message, the copied sentences are dropped before they stream. A run of 80+ characters without punctuation, or a sentence of 16+ characters that already appeared earlier in the same reply, ends the pass and is trimmed (`guard_trim` in the done event); the next hop resumes from the clean text. Immersive sampling uses a flat `presence_penalty` 0.25 over 1024 tokens with frequency and repetition penalties off.
- The composer accepts 5000 characters with a visible counter.
- Theme boot loads from `/theme-boot.js` so production CSP can stay `script-src 'self'`.
- `sysctl` / `vm_stat` sampling never raises: probe order is `which sysctl`, `/usr/sbin/sysctl`, `/proc/meminfo`, then `vm_stat`. Unknown resources never pause generation. The API LaunchAgent PATH includes `/usr/sbin:/sbin`. Quality eval accepts `--profile` / `--max-tokens` / `--timeout` / `--turns` without changing CI defaults.

## v0.6.8 — Account menu sits above the footer

- The account popover opens above the entire sidebar footer, so runtime status stays visible while the menu is open.
- Tight viewports shrink the menu with max-height and scroll instead of covering the status row.

## v0.6.7 — Sidebar footer account menu

- Sidebar footer is two rows: model status, then an account trigger. Theme and logout live in a compact popover.
- Lock remains a backend primitive (`POST /auth/lock`) and is not a default navigation control.

## v0.6.6 — Login form visibility

- Login fields have labels, control-border tokens, and a visible focus ring. Light and dark both keep three surface levels: page, card, input.
- Remember-me stays unchecked. Opaque auth errors stay opaque. No backend auth change.

## v0.6.5 — Explicit exposure mode

- `KILN_EXPOSURE` must be `local` or `private`. Unset refuses startup. Host and `user_count` never select the mode.
- Local mode rejects public, LAN, and HTTPS-proxy Hosts instead of switching to private.
- Private mode CSRF allows only `KILN_PUBLIC_ORIGIN`. Loopback origins are not mixed in.
- `python -m app.cli reset-password` recovers an owner password locally without the previous password. No HTTP reset.
- GitHub Actions installs backend deps from `uv.lock` (`uv sync --frozen`).
- Nginx security headers are a shared include so JSON locations keep HSTS/CSP/XFO.

## v0.6.4 — CI uses repo-root npm test

- GitHub Actions `verify` runs `npm test` from the repository root so pytest uses the root `.venv`.

## v0.6.3 — CI test runner cwd

- `npm test` no longer `cd`s into `backend` before the frontend suite, so Ubuntu CI can finish after pytest.

## v0.6.2 — CI isolation for the private-mode gate

- Injected TestClient chat no longer runs live MLX restore, so Ubuntu CI cannot mark chat `recovery_failed`.
- Hub preflight tests enable downloads explicitly. MLX-only and local-tokenizer tests skip on hosts that lack those files.

## v0.6.1 — Final hardening

- Local-open mode is limited to loopback Hosts (`127.0.0.0/8`, `::1`, `localhost`). RFC1918 and link-local Hosts fail closed with zero users.
- Trusted HTTPS proxy requests cannot inherit local-open by spoofing `Host: 127.0.0.1`.
- Tokenizer load defaults to `trust_remote_code=false`.
- `python -m app.cli change-password` rotates an owner password and revokes sessions.
- Public nginx now writes a kiln-only access log (no cookies/bodies).
- Reverse SSH uses a dedicated `kiln-tunnel` user with `PermitListen 127.0.0.1:17777`.

## v0.6.0 — Private mode and conversational reliability

- Private internet mode is fail-closed: auth is required even with zero users, public Host cannot inherit local open mode, and the first owner is created on the Mac CLI.
- Browser sessions default to a non-persistent cookie with idle and absolute timeouts; “keep me logged in” is an explicit 7-day choice.
- Cookie-authenticated POST/PATCH/DELETE require an allowlisted Origin. Sibling subdomains are not trusted.
- Memory/conversation/generation queries fail closed without an owner. Legacy null-owner rows are assigned only at bootstrap.
- Model download/activate is owner-only. Public deployment serves `web/dist` and an API-only loopback tunnel, not Vite.
- Prompt-cache attribution for mlx-lm 0.31.3: per-request `chat_template_kwargs` does not bypass the LRU when token IDs match; streaming persists the same cache as non-streaming.
- Continue sends `/v1/completions` with a tokenizer-native prefix. mlx-lm 0.31.3 dies on an exact prompt-cache hit; Kiln drops the last token and, on retry, further tokens so the same prefix is not resent. Think-cut uses the same shortening. A leftover exact hit can still kill the generate thread; a silent Continue EOF counts as an inference fault.
- Mid-think Continue uses the official thinking generation prefix plus saved reasoning, not Kiln-built think tags.
- Continue/Regenerate HTTP errors before `meta` no longer remove the last turn from the local UI.
- Dialogue fold runs only when the prompt exceeds the hard profile budget. `prompt_soft_target` is occupancy metadata, not a fold trigger.
- Interactive Dialogue hard prompt cap is 10240 (soft target 8192). Balanced 16384; Reasoning keeps 32768.
- `/health` distinguishes MLX HTTP liveness from inference readiness after repeated timeouts.
- Offline CJK quality metrics and a non-CI long-dialogue evaluation runner.
- 250-turn Interactive Dialogue eval used `max_tokens=192`: warm TTFT p50 1.37s is a cache-hit floor (~96%), not a miss. Everyday/short-reply semantic repetition remains.
- Classify every generation terminal; incomplete upstream streams are no longer stored as a normal stop.
- Interactive Dialogue is the default profile: thinking off, a single `/v1/chat/completions` pass, max output 1536.
- Manual think-cut continuation is opt-in only (`thinking_continuation`), not the default chat path.
- MLX sampling controls (min_p, presence/frequency/repetition penalties and context sizes) are wired through Settings → API → provider.
- Long chats now fold complete turns into a rolling dialogue state/summary instead of first-160-character snippets.
- Memory search and `/memory` are owner-scoped. Retrieval receives a real conversation id.
- SSE heartbeats fire while waiting for the first provider event without cancelling the generator.
- Frontend shows TTFT vs decode tok/s, incomplete-generation copy, Continue, and collapsed advanced sampling.
- OpenAI-compatible streaming classifies EOF/malformed frames instead of emitting a silent successful `[DONE]`.
- Continue resumes an unclosed think block instead of forcing `</think>`.

- Split refusal/censorship claims from prompt-adherence quality. Document each backend’s checkpoint provenance instead of calling Kiln “fully uncensored.”
- Chat sampling now follows the Qwen3.5 card: thinking `0.6/0.95/20`, non-thinking `0.7/0.8/20`, with UI overrides.
- Image and video can compile prompts locally through the running Qwen (enhance before parking chat). Raw mode still sends the user text unchanged.
- Generation cards show Original vs Effective prompt, backend, model, seed, and steps.
- Video Fast keeps the old speed preset; Quality uses more steps, guide 6, shift 8, TeaCache off. Wan2.2 5B is not added on 24GB.

## v0.5.0

- Added local image/video generation with persistent jobs, cancellation, and serialized heavy workers.
- Added chat parking/recovery while video generation uses unified memory.
- Kept the v0.4 Model Workbench and local model activation flow.
- Standardized the local UI entrypoint at `http://127.0.0.1:7777`.
- Added optional reverse-proxy Host allowlisting so a public HTTPS front can reach the loopback UI.
- Documented measured M4 24GB video defaults and scaling limits.

## v0.4.0

- Added the Model Workbench: browse the live Hugging Face catalogue in Kiln, inspect repositories, download MLX-ready checkpoints into a private local library, and select the active model.
- Rebuilt the conversation surface around a compact kiln-room visual system: generated background art, collapsible history, per-conversation delete, message quote/delete, and a context-budget inspector.
- Made model selection restart-safe on the local host and added server-side MLX validation, safe Hub outage handling, activation checks, and deployment safeguards that keep public instances read-only.

## v0.3.0

- Made Kiln model-flexible while making the verified Qwen3.5-9B MLX profile the default.
- Added pinned, checksum-verified model download instructions; removed the unused 27B tokenizer from public deployment.

## v0.2.4

- Added CI validation of the Caddyfile with the official Caddy container image.

## v0.2.3

- Moved the GitHub Actions workflow to Node 24-based official actions to remove the Node 20 runtime deprecation warning.

## v0.2.2

- Made CI create the virtual environment expected by the test command, so clean runners verify the same workflow as local development.
- Made the private deployment environment path configurable for non-secret Compose validation.

## v0.2.1

- Hardened the public-release hygiene: portable deployment helpers, clean Markdown, and CI-ready privacy checks.

## v0.2.0

- Added individual accounts, Argon2id password hashes, hashed sessions, account-scoped conversations, login throttling, and account lockouts.
- Added Caddy-based HTTPS deployment, security headers, and public-source privacy boundaries.
