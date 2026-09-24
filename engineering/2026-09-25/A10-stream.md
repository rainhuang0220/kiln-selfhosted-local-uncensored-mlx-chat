# A10 流式正确性

日期：2026-09-25。只读。没有改 `backend/` 或 `web/`，没有重启 8787，没有点浏览器，没有向 MLX 发请求。

HEAD `0111852169bb5c6ecabafd3733706f58a89c01c0`（`eng/inference-baseline-20260924`，2026-09-24 21:41:38 +0800）。提交说明：Fix streamed continuation tails and the local stop label.

## finding

0111852 只修了两处磁盘行为：`TailStripper` 在下一块分叉时吐回已吞前缀；浏览器 `AbortError` 时立刻把本地气泡写成 `finish_reason=abort`、`terminal_state=interrupted_user`。坏 JSON 之后若仍有合法 `finish_reason` 和 `[DONE]`，账本仍是 `completed_stop` / `completed_length`。0111852 没碰这条路径。**not_done**。

8787（PID 15068）没有加载 0111852。**not_done**（不是 deployed）。已提交不等于已部署。

Stop 的服务端落库在源码里原本就有，而且这份 `chat.py` 与进程启动时一致，所以 **deployed**。它写的是 `messages.finish_reason=abort` 和 `status=cancelled`。没有 `terminal_state` 列。0111852 的「立即」只存在于前端内存，不在 8787 里，也不在 2026-09-15 的 `web/dist` 里。浏览器 Stop **tested_live = not_done**。

没有 SSE 帧序号。`request_id` 只是 context snapshot 的 id，不是逐帧 seq。

`web/src/app.tsx` 仍用 `provider.reachable` 显示「模型暂时离线」（约 464–466、493、661 行）。本任务未改 UI。

## evidence

### 0111852 改了什么

`git show --stat 0111852`：6 个文件，+193 / −5。

| 文件 | 作用 |
| --- | --- |
| `backend/app/services/continuation.py` | `TailStripper._held`，分叉时 `return self._held + text`（74–94 行） |
| `backend/tests/test_continuation.py` | `test_tail_stripper_returns_held_prefix_when_the_next_chunk_diverges` |
| `engineering/2026-09-24/scripts/test_sse_reassembly.py` | 同一分叉断言从 `"dea"` 改为 `"idea"`。函数名仍是 `test_tail_stripper_drops_a_diverging_prefix` |
| `web/src/stores/chat-store.ts` | `AbortError` 分支写 `status/incomplete/terminal_state/finish_reason`（725–737 行） |
| `web/src/stores/chat-store.test.ts` | `marks a user stop as abort without waiting for a reload` |
| `engineering/2026-09-24/agents/A10-sse-protocol.md` | 审计说明。正文写于修复前，开头注明坏 JSON 未改 |

没有改 `stream_protocol.py`、`sse.py`、`mlx.py`、`chat.py`、`main.py`、`app.tsx`。

声称覆盖：续写尾部分叉不再丢字；用户停止不必等重新打开会话才有 abort 字段。坏帧 + finish + `[DONE]` 仍被脚本断言为 `completed_stop`（缺陷仍在，不是修掉了）。

### 8787 加载的不是 0111852

| 项 | 值 |
| --- | --- |
| PID 15068 | `Python -m uvicorn app.main:app --host 127.0.0.1 --port 8787 --proxy-headers --forwarded-allow-ips=127.0.0.1` |
| cwd | `/Users/rainhuang/Desktop/models/kiln/backend`（`lsof -d cwd`）。包名是 `app`，不是 `backend.main` |
| lstart | 2026-09-15 13:08:31。已运行约 9 天 13 小时。PPID 1，无子进程 |
| reload | argv 无 `--reload` |
| 启动时祖先 | `66ff5a7`（2026-09-15 13:08:18，早 13 秒） |
| 0111852 | 2026-09-24 21:41:38，晚于 lstart |

`app.main` 在 import 时拉入 `ChatService` 和 `MlxProvider`。二者在模块顶层 `from app.services.continuation import TailStripper`（`chat.py` 13 行，`mlx.py` 12 行）。uvicorn 访问 `app.main:app` 会在启动时执行这些 import（`main.py` 1201–1203 的 `__getattr__`）。没有 reload 就不会再读磁盘。

`git diff --stat 66ff5a7 HEAD -- backend` 只有 `continuation.py` 和 `test_continuation.py`。`chat.py`、`stream_protocol.py`、`sse.py`、`mlx.py`、`main.py` 与启动时提交内容相同，所以进程里的分类和 Stop 落库与当前这些文件一致。`continuation.py` mtime 是 2026-09-24 21:39:39；`continuation.cpython-312.pyc` 是 21:39:54。pyc 是之后另一次 import 写下的。PID 15068 从 9 月 15 日一直是同一个进程，不会因为 pyc 更新而换掉已在 `sys.modules` 里的类。

`:8000` PID 95938 是 `uvicorn backend.main:app`，cwd `/Users/rainhuang/Desktop/docxeditor`。不是 Kiln，不是 8787。

监听里的 node 5173 / 3000 分别是 locus 和 Flow，不是 Kiln 前端。`web/dist` mtime 2026-09-15 15:02:55。包内 `AbortError` 仍是 `{...de,status:"interrupted"}`，`finish_reason:"abort"` 出现 0 次。8787 的 `main.py` 也不挂静态 `web/dist`。

结论：TailStripper 修复与本地 Stop 标签都是 **implemented**，对 8787 是 **not_done**。

### TailStripper（磁盘已修，进程没有）

`continuation.py` 87–94 行：前缀匹配时 `_held += text` 并返回 `""`；下一块对不上时返回 `_held + text`。调用点仍是 `chat.py` 1162 行（续写）和 `mlx.py` 319–321 行（思考后续写）。进程里的类没有 `_held`。

### Stop

服务端，取消优先于上游 finish（`stream_protocol.py` 75–76、109–120 行）：`cancelled` → `interrupted_user`，库存 finish 是 `abort`，消息状态 `cancelled`。

`chat.py` 1362–1366 行接住 `CancelledError` / `GeneratorExit`，`finally` 1378–1434 行调用 `_finalize_assistant`。SQL（701–707 行）更新 `status`、`finish_reason`、`error`，并插入 `generation_runs.finish_reason`。没有 `terminal_state` 列。`get_conversation`（138–146 行）也不选出它。取消在 `yield done`（1482 行）之前重新抛出，所以客户端收不到带 `terminal_state` 的 `done`。`main.py` 704–706 行只 `aclose` 再抛出。

`backend/tests/test_streaming_cancel.py` 只断言 `status == "cancelled"`，不断言 `finish_reason == "abort"`。`test_stream_protocol.py` 的 `test_user_cancel_wins` 断言账本返回 `abort`，不走数据库。

前端 0111852：`chat-store.ts` 725–737 行在 `AbortError` 时写四个字段，且不走 723 行的 `loadConversations`。这是 zustand，不是 SQLite。乐观 assistant（489–495 行）没有 `usage`。铜字「已中断」画在 `m.usage` 为真的 meta 行里（`app.tsx` 380–395 行）。停止当时若还没有 usage，字段写上了，铜字仍可能不出现。重新打开会话时，`cancelled` 被映射成 `interrupted`（344–347 行），`terminalCopy("abort")` 能显示「已中断」。那条要等服务端落库之后的 reload。

### 坏 JSON 仍标 clean（not_done）

`model_finish_reason` 和传输完整性没有分成两个终态。`StreamLedger` 同时记着 `finish_reason`、`saw_done_wire`、`http_eof`、`malformed_frames`，但 `classify()` 在「可靠 finish + 见过 `[DONE]`」时直接返回完成，坏帧计数被跳过。`to_metrics()` 150 行仍带 `malformed_sse_frames`。网页 `done` 处理（`chat-store.ts` 696–716 行）只看 `incomplete` / `terminal_state`，不看这个计数。

路径：

1. `backend/app/providers/sse.py` 32–35 行：JSON 失败或非 object → `kind="malformed"`。`id:` / `event:` / `retry:` 在 25–26 行被丢掉。
2. `backend/app/providers/mlx.py` 188–190 行：坏帧变成 `__malformed__`，不带正文。
3. `backend/app/services/chat.py` 1136–1138 行：`malformed_frames += 1` 然后 `continue`。正文不加入。
4. 同函数 1174–1175 行：后面的合法帧仍 `observe_finish`。1133–1134 行：`[DONE]` 仍 `observe_done_wire`。
5. `backend/app/services/stream_protocol.py` 85–86 行：只有「有坏帧且没有 finish 且没有 `[DONE]`」才是 `upstream_protocol_error`。
6. 同文件 87–95 行：`length` 或 `stop`/`tool_calls`，并且 `saw_done_wire`，返回 `COMPLETED_LENGTH` / `COMPLETED_STOP`。不读 `malformed_frames`。
7. 113–116 行：`stored_finish_reason` 返回模型的 `stop` 或 `length`，不是传输错误。
8. 123–124 行：`incomplete` 对完成态为 false。105–108 行：消息状态 `complete`。
9. `chat.py` 1484–1487 行：`done` 把这个 finish、`terminal_state`、`incomplete: false` 交给网页。

`engineering/2026-09-24/scripts/test_sse_reassembly.py` 85–91 行把上述结果写成当前行为：`malformed_frames=1` + `observe_finish("stop")` + `observe_done_wire()` ⇒ `COMPLETED_STOP` 且 `incomplete is False`。0111852 保留了这条断言。

正常 mlx 单行 `json.dumps` 不会自己制造坏帧。截断连接通常是坏尾行加 `http_eof`、没有 `[DONE]`，那条已经是协议错误或 `interrupted_transport`。缺口是坏行夹在中间、结束帧仍然合法。

### request_id / sse seq

没有。Kiln 写出只有 `event:` 和 `data:`（`main.py` 148–152 行），没有 `id:`，payload 里没有帧序号。上游 SSE `id:` 在 `sse.py` 25–26 行丢弃。`mlx.py` 222 行只取 `choices[0]`，不按 `index` 重排。重复 delta 会再拼一次。

已有的 id 都不是帧序：

- `chat.py` 1255 行 `snapshot.request_id` = `snapshot_id`。
- `chat-store.ts` 377 行重新打开时用 context snapshot 的 `c.id` 填 `request_id`。
- `mlx.py` 237 行内部 `chatcmpl-{uuid}` 不写进 Kiln SSE 的 `id:`。
- `messages.seq`（`chat.py` 144 行 `ORDER BY seq`）是会话里的消息顺序，不是 SSE 序号。

## proposed change

最小修复点：`backend/app/services/stream_protocol.py` 的 `StreamLedger.classify`。

在 87 行的 `COMPLETED_*` 分支之前：`malformed_frames > 0` 时不要返回 `COMPLETED_STOP` / `COMPLETED_LENGTH`。返回 `UPSTREAM_PROTOCOL_ERROR`（已在 `INCOMPLETE_STATES` 里）。`stored_finish_reason` 会变成 `upstream_protocol_error`，`incomplete` 为真，已收下的正文保持不动。不要把模型的 `finish_reason` 和传输是否干净合成一个「clean stop」。

不要在这个修复里再改 `TailStripper`。不要为了上线去重启 8787。本文件不带补丁。

显示层的剩余缺口（不是这一刀）：`AbortError` 不写 `usage`，而「已中断」渲染依赖 `m.usage`（`app.tsx` 380 行）。那是前端，8787 不加载它。

## risk

Fail-closed：中间夹一行坏 JSON 的生成会从「完成」变成「未完成」，Continue 会出现。正常 mlx 行进不来。注释行是 `keepalive`，不是 malformed。

只改分类，不改表。旧行不会重算。`metrics.malformed_sse_frames` 已经有数，网页现在不展示它。

8787 在重启前继续跑 9 月 15 日的 `TailStripper` 和现在这份分类（分类与磁盘相同，TailStripper 不同）。把磁盘上的 0111852 说成已上线会错。

## tests

跑过，都不碰 8081 / 8787，不加载 pytest `conftest`，不连生产进程：

- `cd backend && ../.venv/bin/python -c` 调用磁盘上的 `TailStripper`：`"i"` + `"dea"` ⇒ `"idea"`。通过。这只证明磁盘，不证明 PID 15068。
- `python3 engineering/2026-09-24/scripts/test_sse_reassembly.py`：8 项通过。其中 `test_finish_plus_done_is_stop_even_with_a_dropped_malformed_frame` 仍要求坏帧后的 stop 是 clean。importlib 按文件加载 `sse.py`、`stream_protocol.py`、`continuation.py`、`heartbeat.py`。
- `cd web && ./node_modules/.bin/vitest run src/stores/chat-store.test.ts`：10 项通过。`apiFetch` 被 mock。覆盖本地 abort 字段，不覆盖铜字是否画出，也不是浏览器点击。

没跑 `npm test` 全套，没跑 `backend` pytest（`conftest.py` 会 import `app.main`，`client` fixture 会起 TestClient；本任务的单测不需要它）。没跑 GPU / MLX。

建议补的测试（未写）：`StreamLedger(malformed_frames=1)` 加 `observe_finish("stop")` 和 `observe_done_wire()` 必须是 `UPSTREAM_PROTOCOL_ERROR` 且 `incomplete`。把 reassembly 脚本里那条「仍是 stop」改成同一期望。`test_streaming_cancel.py` 应断言 `finish_reason == "abort"`。不要用浏览器生产点击当这条的唯一证据。

## rollback

分类修复若只在磁盘：还原 `stream_protocol.py` 即可，无迁移。PID 15068 不受影响，直到有人另行重启。

不要用重启 8787 当作本审计的回滚或发布。重启才会把 0111852 的 `TailStripper` 和任何新分类一起换进进程；回退手段是把进程重新拉到修复前的提交，而不是在这次任务里做。

## status

| 项 | implemented（磁盘） | deployed（8787） | tested_live（浏览器） |
| --- | --- | --- | --- |
| TailStripper 分叉吐回前缀 | 0111852，有 | **not_done** | **not_done** |
| 本地 Stop 立即写 abort / interrupted_user | 0111852，有。`web/dist`（09-15）没有 | **not_done**（进程不跑 TS） | **not_done** |
| 服务端 Stop 落库 `finish_reason=abort`，`status=cancelled` | 有，早于 0111852。无 `terminal_state` 列 | **deployed**（`chat.py` 自 `66ff5a7` 未改，启动时已 import） | **not_done** |
| 坏 JSON 之后不再标 `completed_*` | **not_done** | **not_done**（磁盘就没有，进程也没有） | **not_done** |
| SSE `id:` 或帧 seq | **没有** | **没有** | — |
| snapshot 级 `request_id` | 有，不是帧序 | 有（`chat.py` 未改） | 未点 |
| `provider.reachable` →「模型暂时离线」 | 仍在 `app.tsx` | health 字段在未改的 `main.py` 里，随进程在 | 未点 |
