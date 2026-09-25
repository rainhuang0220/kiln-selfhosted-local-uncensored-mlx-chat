# Live deployment and browser check — 2026-09-25

## Versions and safety

- Backend code deployed from `cf2dee9` by restarting only `com.kiln.api`.
  API changed PID 97690 → 56499; MLX remained PID 1581 on port 8081.
- Public frontend assets were built from `a672a2f`; the published HTML
  references `index-CJGbwbMg.js`. The older public HTML referenced
  `index-BpRzQfzR.js` before this wave.
- A SQLite online backup was made before the API restart at
  `../kiln-backups/2026-09-25/chat-before-full-document-and-runtime.db`.
  Its `PRAGMA integrity_check` returned `ok` (2,203,648 bytes).
- Public static files were backed up on the VPS at
  `/home/ubuntu/kiln-backups/web-before-cf2dee9.tar.gz` (633 KiB).
  Existing files were preserved when new fingerprinted assets were copied.

## Observed behavior

The old public site called `/health`, which Nginx intentionally returns 404;
its old build showed “模型暂时离线” to a signed-in user while local MLX HTTP was
reachable. Backend now serves the same health data at authenticated
`/auth/runtime`, which the existing Nginx `/auth` route proxies. An anonymous
public request to `/auth/runtime` returned 401. The signed-in public browser
then showed “端口在线” for an expired `UNVERIFIED` generation observation.
After a real generated reply it showed “模型在线”. The final text for expired
evidence is “近期生成尚未验证”; this avoids claiming there was never a prior
successful generation.

A signed-in Chrome browser sent `只回复 KILN-OK，不要添加其他文字。` through
`https://kiln.plainlist.space/`. The reply was `KILN-OK`; browser metrics:
25 input tokens, 6 output tokens, 0 cached, TTFT 2,835 ms, decode 18.2
tokens/s. Local `/health` then reported `READY`, `ready=true`, and
`verification_method=user_generation`. Swapouts stayed at 74,464,192 pages
across the short generation.

In the same public browser, a roughly 300-character writing request streamed
partial text. Stop changed the message to “已中断”. After page refresh and
reopening the conversation, the same partial assistant message persisted with
94 output tokens and a Continue button. Continue completed it in place. The
database contains one assistant message for that writing request (308 Unicode
characters), not a second assistant message. The visible continuation joined
at the original sentence without an obvious repeated span. Its second call
reported 161 input tokens, 114 output tokens, 64 cached, TTFT 1,648 ms, and
decode 15.8 tokens/s.

Chrome file attachment of `eval/semantic-20k.txt` could not be completed:
the file chooser first lost its debugger connection; a fresh tab then returned
`Not allowed` when asked to attach the local path. Browser file URL access for
the ChatGPT extension is not enabled. No semantic 20K browser quality result
is claimed from this route.

The authenticated browser instead submitted a separate synthetic full-text
prompt containing 20,000 repetitions of `窑` followed by `文末标记：MARK8841。`.
The production tokenizer counts `窑` as one token here. Kiln's recorded prompt
was 20,032 tokens, with a 32,768-token effective budget. The persisted
snapshot contained all 20,000 repeated characters plus the final marker;
`truncated=0` and no packed-document wrapper. The model returned `MARK8841`
with a normal `stop` terminal and browser TTFT 99,280 ms, decode 17.6
tokens/s. This tests full-input transport and a simple tail fact, not semantic
long-document understanding. Swapouts rose from 74,479,900 to 74,603,688
16-KiB pages during the long request: 123,788 pages, about 1.89 GiB. The
five-second preflight window had zero swapouts. Video pause and timed recovery
were not exercised on the production MLX.

## Rollback

The prior API commit is `2bfe465`. With a clean checkout, switching to that
commit and running `launchctl kickstart -k gui/$(id -u)/com.kiln.api` rolls
back this backend wave without touching MLX; switch back to
`eng/inference-baseline-20260924` and kickstart the API to return. The earlier
`deploy-and-rollback.md` documents an actual API backward/forward drill to
`c22d1c3`/`486d774`; this exact `cf2dee9` rollback has not been run.

For the public site, the VPS archive above contains the previous static tree.
An operator can restore it with `sudo tar -C /www/wwwroot -xzf
/home/ubuntu/kiln-backups/web-before-cf2dee9.tar.gz` over SSH and verify that
the old `index.html` hash is served. This rollback has not been run in this
wave. Neither rollback needs an MLX restart or a database rollback.
