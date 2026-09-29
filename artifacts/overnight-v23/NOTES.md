# Night V23 — Phase 0 inventory (parent 8d4821d)

## Ops at start
- MLX PID 2329 had a dead `_generate` thread since 03:18:49 (IndexError in
  `BatchGenerator.insert_segments`, `seq[-1]` empty, on a `/v1/completions`
  continue hop). `/v1/models` 200, path-id 8-token probe 0-byte for 60 s.
  One `launchctl kickstart -k gui/$UID/com.kiln.mlx` → PID 33389, probe ok in ~1 s.
- API :8787 PID 13405, profile immersive, default_max_tokens 6144.
- Live evals run on an isolated worktree API on :8797 (temp sqlite, bogus
  MLX launch label so it can never bootout/kickstart com.kiln.mlx).

## Current fence recipe (IR v2 bound, default hop)
`router.route_context`:
1. L0 `<active_context>` ≤400: persona role, current_scene (twice: 重点现实场景 + current_scene), user_avatar.
2. L2 `<service_requirements do_not_literalize>` ≤320 (total ≤720): persona.rules,
   live ROLE_DEFINITION clauses, pref-manual, USER_PREFERENCE segs, preference bank.
   Parenthesised 风格参考 lines are segment type UNKNOWN / scope reference on the
   rules path → they never enter the block. On the overnight fixture the block has
   0 items (header + role line only).
3. chat._build_user_fences: `style_fence = None if has_ir else style.fence()` —
   **StyleBank.fence is skipped whenever IR v2 is bound**; also style_bank_for_preset
   returns an empty bank for the fixture.
4. Author note switches to CONTEXT_IR_AUTHOR_NOTE (no sensory line; "不补写未经提供的…细节").
5. System prompt: `compile_system(grounded_context=True)` for any preset →
   GROUNDED_CONTEXT_SYSTEM clause 3 forbids inventing 光线、气味、衣着、身体特征 —
   actively suppresses 文爱 sensory writing. Clause 4 "首轮保持紧凑".

## Sampling
- IMMERSIVE: temp 0.78, top_p 0.9, top_k 40, min_p 0.05, presence 0.25 / ctx 1024,
  frequency 0, **repetition_penalty 1.0** (→ mlx 0.0 = off), ctx 256.
- Web client sends `repetition_penalty: 1.0` explicitly (lib/profiles.ts) and
  `auto_continue: true` for immersive, so a backend profile change alone does not
  reach UI users; resolve_sampling lets client values override the profile.

## Hop / refund rules
- min_output_chars 5000, auto_continue_max 5, completion_soft_cap 12288,
  provider-call hard cap 6.
- Preset first turn: min_output_chars → 0 only when `auto_continue is None`
  (API default). The web UI sends auto_continue=true, so the 5000 floor applies.
- Fill hop: when 0 < visible < floor on a continue, EOS/im_end banned via
  logit_bias -100 and max_tokens sized to floor+1200 → the 9B cannot stop, so it
  repeats the last action until `repeated_sentence_start` (≥16-char sentence reuse)
  or `hard_self_loop` (3 consecutive ≥40-char sentences) cuts it.
- Guard-aborted hop with <80 unique chars is refunded (does not count).
- Below the floor, stub_streak does not stop Continue.
- `runon_start` cuts an ≥80-char unpunctuated tail.
- chat idle: first token 45 s, between tokens 20 s.
