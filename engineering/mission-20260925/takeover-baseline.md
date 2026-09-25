# Takeover baseline — 2026-09-25 16:50 CST

This is a live-state snapshot, not an acceptance claim. Git started clean at
`2bfe465` on `eng/inference-baseline-20260924`; no push was made. MLX PID 1581
has listened on `127.0.0.1:8081` since September 11. API PID 97690 has listened
on `127.0.0.1:8787` since 13:16 today. The API process has no embedded Git
revision. Its probe fields establish that it loaded at least the `7eed604`
behavior; changes committed later are not proven loaded. The previous ledger's
`api_loaded_commit=486d774` is stale.

At takeover, local `/health` said MLX HTTP reachable and gateway AVAILABLE,
but inference `UNVERIFIED`, `ready=false`. The last successful probe expired at
13:31. An expired success is not a current generator failure. The public Nginx
configuration deliberately returns 404 for `/health`, while the older public
web build asks for `/health`. In the existing signed-in public Chrome tab this
rendered the old “模型暂时离线” message even though local MLX HTTP was reachable.
`/auth/status` is proxied. The new authenticated `/auth/runtime` path is being
implemented so the browser can read the same health snapshot without making
the public `/health` endpoint available.

The existing 20,000-character semantic document was 13,240 prompt tokens in
the recorded cold full-text run (62.754 s); a distinct 20,000-token-scale run
is in `prefill-ladder.md`. Both are direct MLX observations. The latest 50-item
semantic score is 28 exact, 18 numeric but incomplete, two incomplete quotes,
and two wrong arithmetic answers. Those items are shorter documents, not 50
questions on a single 20K document. `context_route.py` is tested in isolation
but not called by `chat.py`; production packs oversized messages using
`ingest.pack_user_message`. The recorded 0.588 s repeat used 13,236 cached
tokens and cannot stand for cold input performance.

The 30-item behavior run recorded nonempty responses without a refusal opener,
not a full content-quality grade. Independent disk recheck still found zero
qualified deletions across the protected 30-path inventory. The two 27B trees
share APFS clone storage. The Qwen2.5-1.5B learning model and image/video
weights remain protected.

User requirements are stable generation, no extra moderation proxy, full
20K-character and 20K-token tasks, useful context optimization, intact stream
ordering, and safe cleanup. G0–G8 are engineering acceptance gates. The 2x
cold end-to-end TTFT target is a research/performance goal for applicable
fast-path tasks; it does not justify dropping evidence or declaring full-text
prefill twice as fast. All unmeasured live gates remain open.

Evidence: `acceptance.json`, `speed-paths.md`, `prefill-ladder.md`,
`eval/README.md`, `deploy-and-rollback.md`, `disk-dependency.md`,
`backend/app/services/chat.py`, `backend/app/services/ingest.py`,
`backend/app/services/context_route.py`, `web/src/stores/chat-store.ts`, and
`deploy/nginx-kiln.plainlist.space.conf`.
