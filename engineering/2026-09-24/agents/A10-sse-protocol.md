# A10：MLX → 后端 → 网页的 SSE

日期：2026-09-24。审计时没有改 `backend/` 或 `web/`。HEAD 当时是 `ui/account-menu-placement` @ `0a4322de9a506b54411af2ed10f8c081e73ba003`。

总控随后修了两处：`TailStripper` 在下一块分叉时把已经吞下的前缀吐回；用户点停止时，气泡立刻写上 `finish_reason=abort` 和 `terminal_state=interrupted_user`。坏 JSON 仍可能被记成 `completed_stop`，那一处没有改。下面的正文是修复前的审计。

`git merge-base --is-ancestor a6a4d2e HEAD` 退出码 0。`a6a4d2e`（`feat/conversational-reliability`，streaming integrity）是当前 HEAD 的祖先。自那次提交之后，`backend/app/providers/sse.py`、`backend/app/services/heartbeat.py`、`backend/app/services/stream_protocol.py`、`web/src/api/stream.ts` 没有再改。`chat.py` / `mlx.py` 后来为续写加了 `TailStripper`。

模拟在 `engineering/2026-09-24/scripts/test_sse_reassembly.py`。`python3` 跑通 8 项。取消路径另用仓库 `.venv` 的 Python 3.12 + anyio 跑了 30 次。记录在 `engineering/2026-09-24/raw/A10/repro.txt`。

## 结论

旧问题已经在这条祖先链上修好了：HTTP EOF、只有 `data: [DONE]`、或者只有 `finish_reason` 而没有 `[DONE]`，都不会再被记成正常 `stop`。`/chat` 上客户端断开会关掉嵌套生成器，不会把 provider 留在 `asyncio.sleep` 那种挂起里（30/30）。UTF-8 在 TCP 块边界被拆开时，后端和浏览器都能拼回，不会把半个「你」解析成坏帧。

这条链没有 SSE `id:`，也不按 `choices[].index` 重排。重复 delta 会原样再拼一次。mlx-lm 0.31.3 正常输出是按序的单 choice，不会自己制造乱序 id。

本提交仍在的具体缺陷：

1. 续写 / 思考续写的流式去重 `TailStripper`，在尾部只匹配上一个前缀、下一块就分叉时，已经吞掉的前缀不会吐回来。非流式的 `strip_regenerated_tail` 不会丢这几个字。
2. 用户点停止时，网页只把气泡标成 `interrupted`，不写 `finish_reason` / `terminal_state`。服务端同一条路径会落成 `cancelled` / `abort`。铜字「已中断」要等重新打开会话才出现。
3. 上游坏 JSON 行被丢掉之后，只要后面还有可靠的 `finish_reason` 和 `data: [DONE]`，账本仍记 `completed_stop` 或 `completed_length`。mlx 正常的 `json.dumps` 行不会走进来；一旦中间夹了一行坏 JSON，丢字仍会被标成完成。

## 事件协议

安装的是 mlx-lm 0.31.3（`.venv/lib/python3.12/site-packages/mlx_lm/server.py`）。流式正文是 OpenAI chunk，不是 Kiln 的 `event:` 名：

- 预填阶段可以写注释行 `: keepalive {done}/{total}`（`server.py:1410-1414`）。这发生在 worker 把进度放进队列之后；HTTP 头在 `handle_completion` 开始迭代之前就 `end_headers()`，所以注释在 body 里，不会写在状态行前面。
- 每个可见片段一行 `data: {object: chat.completion.chunk, choices[0].delta.content 或 reasoning, finish_reason: null}`。写完就把本段 `text` / `reasoning_text` 清掉（`server.py:1478-1493`），所以是增量，不是累计全文。
- 结束帧带 `finish_reason`：`stop`、`length`，工具调用时改成 `tool_calls`（`server.py:1504-1514`）。
- `stream_options.include_usage` 时再来一帧 `choices: []` 的 usage（`server.py:1516-1525`，`completion_usage_response` 在 `1554`）。
- 最后 `data: [DONE]`（`server.py:1527`）。
- 控制序列有一个按 stop 词长度的滞回缓冲（`server.py:236-249`）。匹配到的 token 文本被抹成空串，其余按原顺序吐出。这是延迟，不是重排。
- BPE detokenizer 在多字节 UTF-8 还没齐（解码结果以 U+FFFD 结尾）时不把这段交给 `text`（`tokenizer_utils.py:212-218`）。Kiln 看到的 JSON 里已经是完整字符。

Kiln 读这些帧的入口是 `MlxProvider._stream_post`（`backend/app/providers/mlx.py:177-200`）→ `iter_sse_frames`（`backend/app/providers/sse.py:39-50`）。

| 上游 | Kiln 内部 chunk | `/chat` 写出 |
| --- | --- | --- |
| `data: {json}` | `delta_content` / `delta_reasoning` / `finish_reason` / usage | `event: delta`，reasoning 和 content 各一帧 |
| `: ...` | `keepalive` | `event: ping` |
| `data: [DONE]` | `wire_done`，然后 `_stream_post` return，不再发 `http_eof` | 不转发这行；应用自己的 `event: done` 之后另写一行 `data: [DONE]` |
| 迭代结束且没见过 `[DONE]` | `http_eof=True` | 不当成 stop |
| 非法 JSON 或非 object | `malformed=True`，跳过文本 | 不产生 delta |

`/chat` 的字节格式在 `backend/app/main.py:148-152`：`event: {name}\ndata: {json}\n\n`，只用 LF。事件顺序是 `meta`、`snapshot`、零个或多个 `ping`/`delta`、失败时 `error`，成功或「有正文的不完整结束」时 `usage` 然后 `done`（`backend/app/services/chat.py:1242-1270` 与 `1481-1503`）。`event_stream` 在生成器正常结束后再追加 `data: [DONE]\n\n`（`backend/app/main.py:694-703`）。心跳默认 15 秒（`backend/app/config.py:77`），帧是 `event: ping` / `{"ok": true}`，不带 `content`。

`done` 的数据里有 `finish_reason`、`terminal_state`、`incomplete`、`message`（全文）、`usage`、`metrics`。终端状态在 `backend/app/services/stream_protocol.py:74-121`：

- `stop` 或 `tool_calls`，并且见过 `[DONE]`（`saw_done_wire`）→ `completed_stop`，库存 finish 用上游原因。
- `length` + `[DONE]` → `completed_length`，消息状态仍是 `complete`，但 finish 保持 `length`，网页可以继续。
- 有 `finish_reason` 但连接在 `[DONE]` 之前结束（`http_eof`）→ `interrupted_transport`，不是 stop。
- 只有 `[DONE]`、没有 finish → `upstream_protocol_error`。
- 只有 EOF → `interrupted_transport`。
- 用户取消（`CancelledError` / `GeneratorExit`）优先于上面所有情况 → `interrupted_user`，库存 `abort`，消息状态 `cancelled`。
- 未知的 finish 字符串即使带着 `[DONE]` 也落在 `unknown_terminal`，不会被收成 stop。

网页 `readSse`（`web/src/api/stream.ts:6-96`）按空行分帧，认 `event:` 和 `data:`。`data: [DONE]` 变成内部事件 `done_wire`，不叫 `done`。已经见过应用级 `done` 时，`[DONE]` 只是结束读取；没见过则合成 `transport_eof`，原因 `done_wire` 或 `eof`（`stream.ts:63-75`、`79-81`）。`ping` 原样交出，store 直接 `continue`（`web/src/stores/chat-store.ts:642-643`）。

`/v1/chat/completions` 不走这套 `event:` 名。不入库的 `oai_stream` 把 keepalive 丢掉（没有 content / reasoning / usage 就 `continue`，`backend/app/main.py:1018-1023`），结束时仍写一帧 `finish_reason` 加 `data: [DONE]`（`1053-1055`）。这里的 finish 用的是账本值，EOF 会变成 `interrupted_transport`，不是假的 `stop`。网页聊天不走这条。

## 顺序

没有重排缓冲。三层都是到达顺序：

- `iter_sse_frames` 按 `\n` 切，一行一个帧。`id:`、`event:`、`retry:` 直接丢掉（`sse.py:25-26` 非 `data:` 且非 `:` 注释就返回 `None`）。
- `_chunk_from_event` 只取 `choices[0]`，不看 `index`（`mlx.py:222-230`）。同一帧里若有 index 1 再 index 0，index 0 的文本被丢弃。mlx 0.31.3 的 `generate_response` 只写 index 0。
- 网页把 delta 按读到的顺序 `+=`（`chat-store.ts:597-600`）。`done` 时用 `message.content` 覆盖界面上的全文（`707`），但本地累加变量 `content` 不改。模拟里如果 `done` 把界面改成 `Z` 之后又来一个 delta `Q`，界面会变成 `AQ` 而不是 `ZQ`。当前服务端不会在 `done` 之后再 yield delta；这是缺的防护，不是这条链已经在发的顺序。

控制词滞回和 `TailStripper` 会让若干 token 晚一点出现，晚到的仍是原来的相对顺序。

## 重复

没有事件 id，没有已见集合。同一条 `data:` 来两次，后端 `content_buf` 加两次，网页也加两次。`done.message.content` 来自同一个 buffer，所以结束时的全文不会比服务端更干净。模拟：两帧「甲」再 `done`「甲甲」，最终就是「甲甲」。

下面这些不会造成重复，代码是分开的：

- mlx 每个 chunk 只带本段增量，写完清空（`server.py:1491-1493`）。最后一帧在文本已经清空时只有 `finish_reason`。
- completions 用 `choice.text`，chat 用 `delta.content`，`text or content` 只取一个（`mlx.py:224`）。
- reasoning 和 content 进两个字段。`stream_after_think` 只在「有 reasoning、没有 content」时把 reasoning 改记成 content（`mlx.py:309-318`），不会两个字段各记一份。
- 心跳和 `: keepalive` 变成 `ping`，store 不拼进正文。
- `done` 覆盖的是界面文本。思考标签若被 `split_thinking` 挪走，发生在 delta 都已经发出去之后、`done` 之前（`chat.py:1350-1353`）。正常收完时网页会被 `done` 改成切分后的全文。
- 续写成功时，服务端只流新增量，`done.message.content` 是「旧前缀 + 新增」。store 的 continue 用例把同一条 assistant 收成 `partial more`，不插第二条（`web/src/stores/chat-store.test.ts:154-177`）。

续写去重本身有一个会丢字的缺陷，见下一节。它的目的是去掉模型重吐的那个被丢掉的 prompt token，不是 SSE 重放。

## 取消

网页 `stop()` 只 `AbortController.abort()`（`chat-store.ts:436-438`）。`fetch` 和 `readSse` 共用这个 signal（`515-517`、`560`）。`readSse` 在每次 `read()` 前如果已经 aborted，抛 `AbortError`，`finally` 里 `reader.cancel()`（`stream.ts:55-57`、`90-95`）。`read()` 自己因 abort 拒绝时，本地 `aborted` 标志还是 false，但异常会冒出生成器，不会再补一帧 `transport_eof`。store 的 `AbortError` 分支只把 `status` 设为 `interrupted`（`724-729`），不写 `finish_reason`，也不写 `terminal_state`。`terminalCopy` 只看这两个字段（`web/src/lib/profiles.ts:75-80`），所以气泡上没有「已中断」。`Continue` 仍会出现，因为 `status === "interrupted"` 单独就够（`web/src/app.tsx:411-418`）。这次失败路径不调用 `loadConversations`，本地气泡不会被库里的行换掉。

服务端这条是关干净的。`/chat` 的 `event_stream` 在 `CancelledError` / `GeneratorExit` 里 `aclose` 心跳包装，也在 `request.is_disconnected()` 时主动 `aclose`（`main.py:697-706`）。心跳的 `finally` 取消还没完成的 `__anext__` 任务，再 `aclose` 聊天生成器（`heartbeat.py:30-42`）。`chat()` 把这两种异常记成 `ledger.cancelled`，`finally` 里 `_finalize_assistant` 并 `_busy.discard`（`chat.py:1362-1366`、`1435-1436`）。`consume_stream` 的 `finally` 再 `aclose` provider（`1184-1187`），`async with client.stream` 会关掉到 mlx 的 HTTP。mlx 的 `handle_completion` 在 `finally` 里 `ctx.stop()`（`server.py:1551-1552`），生成线程看到 `_should_stop` 后退出。

当前 venv 里的 uvicorn 声明 ASGI `spec_version` `2.3`（`uvicorn/protocols/http/httptools_impl.py:228`）。Starlette 对 `< 2.4` 用 task group 同时等 body 和 `http.disconnect`，断开就取消 body（`starlette/responses.py:267-280`）。用这个取消方式、按 `event_stream` 的「`aclose` 然后重新抛出」跑 30 次：provider 的 `finally`、chat 的 `finally` 都执行，没有残留 task。直接 `aclose()` 把 assistant 标成 `cancelled` 并清掉 `_busy`，仓库测试已经覆盖（`backend/tests/test_streaming_cancel.py:4-16`）。

nginx 对 `/chat` 关了 `proxy_buffering`（`web/nginx.conf:34`，`deploy/nginx-kiln.plainlist.space.conf:72-74`），客户端 TCP 关闭可以传到 uvicorn。没有在公网上对一条活的生成做断开实验。

`/v1` 的 `oai_stream` / `persisted` 没有心跳，也没有 `is_disconnected()`。它们靠上面的 Starlette 取消把 `async for` 收掉。同一套嵌套在直接迭代 provider 时，`async with` 会释放锁、provider `finally` 会跑。网页不用这两条。

## UTF-8

拆开的多字节序列不会被当成一行坏 JSON。

- mlx 的 BPE/SPM detokenizer 把不完整 UTF-8 留在自己的缓冲里，不放进 SSE 文本。
- httpx 0.28.1 的 `aiter_text` 用 `codecs` 增量解码器，`errors="replace"`（`httpx/_decoders.py` 的 `TextDecoder`）。未完成的序列会留到下一块；只有非法字节或流结束时的残余才会变成 U+FFFD。`MlxProvider` 用的是 `resp.aiter_text()`，不是按块 `decode` 一次。
- `iter_sse_frames` 在字符串上拼到 `\n` 才解析（`sse.py:40-47`）。半行 JSON 留在 `buffer`。
- 浏览器 `TextDecoder` 使用 `{ stream: true }`，结束时再 `decode()` 冲掉（`stream.ts:29`、`61`、`78`）。

模拟把「你好」从「你」的第一个 UTF-8 字节切开，经增量解码再进真正的 `iter_sse_frames`，得到一帧 `content == "你好"`，没有 U+FFFD。按 3 字节切开 Kiln 的 `event: delta` 帧，网页侧移植同样得到「你好」。连接在 `done` 之前结束时，这几个字保留，并多一帧 `transport_eof`，不是 `done`。

非法字节是另一件事：替换字符如果还留在 JSON 字符串里面，这帧仍是合法 JSON，后面的 `stop` + `[DONE]` 会把消息标完成。Kiln 没有把 httpx 解码改成 `strict`。这不是拆包错误。

`readSse` 在每个 chunk 上替换 `\r\n`，不是在拼好的 buffer 上替换（`stream.ts:35`）。把数据行结尾的 `\r` 和 `\n` 分到两个 chunk 时，`data` 行会留下尾部 `\r`。`JSON.parse` 允许尾随空白，这个 `\r` 不会让解析失败。用 node 确认过 `JSON.parse('{"content":"雨"}\r')` 成功。Kiln 自己的写出又是 LF。这条不是丢字路径。

## 仍在的缺陷

### 1. 流式 TailStripper 丢掉分叉前缀

`backend/app/services/continuation.py:77-89`。调用点：普通续写的 `consume_stream`（`chat.py:1162-1163`），以及 `stream_after_think`（`mlx.py:319-321`）。`shorten_until_unused` 至少丢掉一个 token，重复续写会丢掉更多，所以 tail 可以跨多个 delta。

`pending.startswith(text)` 时把这块吃掉并返回 `""`，不保留原文。下一块既不是剩余 tail 的前缀、也不以剩余 tail 开头时，`pending` 被清空，函数只返回新块。已经被吃掉的前缀没有了。

实测：tail `"ing"`，块 `"i"` 然后 `"dea"`，输出是 `"dea"`。非流式 `strip_regenerated_tail("idea", "ing")` 返回 `"idea"`（`continuation.py:68-71`）。对齐的拆分 `"i"` + `"ng more"` 正确得到 `" more"`，单块 `"idea"` 也会整块保留。丢字只发生在「先命中真前缀，随后分叉」。

模型若把被丢掉的 token 原样重吐，现有测试（`backend/tests/test_continuation.py:63-66`）是对的。模型没重吐、且第一个 delta 只是 tail 的前缀时，续写结果少一段。

建议：把已经吃下的前缀放在 `held` 里。整段 `held` 以 tail 开头才剥掉 tail；一旦不可能再匹配，把 `held` 原样吐出并清空。不要改非流式函数的语义。未应用。

### 2. 停止按钮的终端字段和库不一致

服务端取消：`finish_reason = "abort"`，`terminal_state = interrupted_user`，`status = cancelled`（`stream_protocol.py:75-76`、`109-120`；`chat.py:1362-1366`）。

网页取消：`chat-store.ts:724-729` 只改 `status: "interrupted"`。`profiles.ts:80` 的「已中断」不会出现，直到用户重新打开会话、从库里把 `abort` 读回来。生成器是停了的，这是展示和本地状态，不是 mlx 还在跑。

建议：`AbortError` 分支同时写 `finish_reason: "abort"`、`terminal_state: "interrupted_user"`、`incomplete: true`。未应用。

### 3. 坏帧不阻止 completed_*

`chat.py:1136-1138` 增加 `malformed_frames` 后 `continue`，正文不加入。`stream_protocol.py:85-98` 只有在「有坏帧且没有 finish 且没有 `[DONE]`」时才返回 `upstream_protocol_error`。finish 是 `stop`/`length`/`tool_calls` 并且见过 `[DONE]` 时，坏帧计数被跳过，结果是 `completed_stop` 或 `completed_length`，`incomplete` 为 false。`metrics.malformed_sse_frames` 有数（`stream_protocol.py:150`），网页的 `done` 处理不看它。

正常 mlx 行是 `json.dumps` 的单行，不会主动制造这种帧。截断连接通常是「坏的尾行 + `http_eof`、没有 `[DONE]`」，那条已经走协议错误或传输中断（`test_stream_termination.py:68-79`）。漏洞是：坏行夹在中间，后面的结束帧仍然合法。

建议：`malformed_frames > 0` 时不要返回 `COMPLETED_*`，把 `incomplete` 设为真（或直接 `upstream_protocol_error`），正文照常保留。未应用。

## 已经修好，不要再当成现存 bug

- EOF 不是 stop。`sse.py:1`；`_stream_post` 在没有 `[DONE]` 时 yield `http_eof`（`mlx.py:196`）；账本在 `stream_protocol.py:90-102`。测试：`backend/tests/test_stream_termination.py:11-33`，`backend/tests/test_stream_protocol.py:32-48`，`web/src/api/stream.test.ts:15-20`。网页把 `transport_eof` 标成 `interrupted_transport` 并保留 partial 文本（`chat-store.ts:644-656`，`chat-store.test.ts:85-99`）。
- 只有 `[DONE]`、没有 finish，是 `upstream_protocol_error`，不是 stop（`test_stream_termination.py:36-48`）。
- 有 `finish_reason: stop` 但没有 `[DONE]`、连接先断，仍是 `interrupted_transport`（`test_stream_protocol.py:32-37`）。
- `length` + `[DONE]` 是完成，但是另一种完成，finish 保持 `length`（`test_stream_termination.py:51-65`）。网页不把它显示成错误条（`chat-store.test.ts:102-115`）。
- 客户端 `aclose()` 会落库 `cancelled` 并释放 `_busy`（`test_streaming_cancel.py:4-16`）。上面的 30 次 anyio 取消也关到了 provider。
- 续写不插第二条 user/assistant，成功时不会把旧前缀再贴一遍（`test_stream_termination.py:127-160`，`chat-store.test.ts:154-177`）。丢字是 TailStripper 分叉，不是整段重复。

## 测试

`python3 engineering/2026-09-24/scripts/test_sse_reassembly.py`（在 `/Users/rainhuang/Desktop/models/kiln` 下即绝对路径 `.../kiln/engineering/2026-09-24/scripts/test_sse_reassembly.py`）。8 项都通过。它加载真实的 `sse.py`、`stream_protocol.py`、`continuation.py`、`heartbeat.py`，并移植了 `readSse` 的分帧。覆盖：UTF-8 从码点中间切开、半行 JSON、EOF 不合成 `[DONE]`、坏帧 + finish + `[DONE]` 仍是 `completed_stop`、重复 `id: 2` 和后到的 `id: 1` 拼成 `BBA`、TailStripper 分叉丢 `"i"`、CR/LF 拆开仍得到「雨」、`done` 之后的 delta 覆盖权威全文、`aclose` 让嵌套 provider 的 `finally` 运行且没有残留 task。
