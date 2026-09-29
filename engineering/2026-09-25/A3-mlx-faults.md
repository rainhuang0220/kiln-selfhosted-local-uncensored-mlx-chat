# A3 MLX 故障（只读）

日期：2026-09-25。未升级 mlx / mlx-lm，未改 site-packages，未向 8081 发送生成请求，未对 PID 1581 做故障注入，未重启。`--help` 是另一个短命进程，停在 argparse，没有加载 9B，也没有监听端口。

PID 1581 仍是 2026-09-11 19:50:33 拉起的那一只。`ps` 里的映像是 Homebrew Python.app，因为 `.venv/bin/python` 链到该二进制，且环境有 `__PYVENV_LAUNCHER__=/Users/rainhuang/Desktop/models/kiln/.venv/bin/python`。`pyvenv.cfg`：`version_info = 3.12.12`，`include-system-site-packages = false`。启动脚本是 `~/Library/Application Support/kiln/start-mlx.sh` 的 `exec …/.venv/bin/python -m mlx_lm.server`。

`.py` 导入后会关掉，`lsof -p 1581` 里没有 `server.py`。同一张表里的扩展库 inode 与这份 venv 文件一致：

| 映射 | inode |
| --- | --- |
| `…/site-packages/mlx/core.cpython-312-darwin.so` | 34738696 |
| `…/site-packages/mlx/lib/libmlx.dylib` | 34742918 |

cwd `/Users/rainhuang/Desktop/models/kiln` 下没有会挡住导入的 `mlx_lm/`。3.12 路径上只有这一份 `server.py`。`/opt/homebrew/lib/python3.14/site-packages/mlx_lm/server.py` 是另一棵树，PID 1581 不会导入。

## finding

运行中的包就是 kiln `.venv` 里的 mlx 0.32.1 / mlx-lm 0.31.3。和 `.venv` 的 METADATA 是同一份，不标红。`/health` 不检查生成线程。精确 prompt-cache 命中把 segment 弹空后，`insert_segments` 的 `IndexError` 仍能打死生成线程，HTTP 仍返回 200。这是这份已加载源码里的路径，不是 2026-09-25 的新崩溃。server CLI 有 `--draft-model`，没有 `--kv-bits`。9B 是 hybrid 文本模型；检查点里虽有 vision tower 权重，聊天路径只传文本，mlx-lm 加载时丢掉视觉权重。它不是生图模型。

## evidence

版本与文件：

| 项 | 值 |
| --- | --- |
| mlx | 0.32.1（`mlx-0.32.1.dist-info/METADATA`） |
| mlx-lm | 0.31.3（`mlx_lm-0.31.3.dist-info/METADATA`，`mlx_lm/_version.py`） |
| server.py | `/Users/rainhuang/Desktop/models/kiln/.venv/lib/python3.12/site-packages/mlx_lm/server.py` |
| sha256 | `cdfcb4ac848636f9927851a0ec7a951584526530cb7832ba58049e4a9144db8b` |
| mtime | 2026-08-23 01:05:39（早于进程启动；磁盘文件即当时导入的那份） |
| 现场参数 | temp 1.0，top-p 0.95，top-k 20，decode/prompt concurrency 1/1，prefill-step-size 1024，prompt-cache-size 4，prompt-cache-bytes 4G，`enable_thinking` false。命令行没有 `--draft-model`，也没有 `--kv-bits` |

`.venv` 对比：运行中的 mlx 扩展库就是 `.venv` 这份。版本一致，不标红。Homebrew Python 3.14 的 site-packages 也装了同号的 mlx 0.32.1 / mlx-lm 0.31.3，但是未加载的另一份。

`/health`：`APIHandler.do_GET`（`server.py` 1620–1631）在路径正好是 `/health` 时调用 `handle_health_check`（1633–1641）。该函数只 `_set_completion_headers(200)` 并写 `{"status": "ok"}`。全文件没有 `_generation_thread.is_alive()`。线程只在 `ResponseGenerator.__init__` 创建并 `start`（451–452），`stop_and_join` / `join` 只是 `join`（454–459）。Kiln 侧 `MlxProvider.health`（`backend/app/providers/mlx.py` 57–63）把这个 HTTP 200 当成存活；URL 来自 `Settings.mlx_health_url`（`backend/app/config.py` 120–124）。

生成线程：`_generate`（688 行）的 `while not self._stop`（717 行）没有外层 `try`。能接住异常的只有 `_tokenize`（737–743）和 `load`（805–811）。`insert_segments` 在这两段之外（776–784），异常不会放回 `rqueue`。HTTP 在 `ThreadingHTTPServer.serve_forever`（1702–1729），与生成线程不是同一条。`/health` 不进入 `generate()`（1026 行起），所以不会堵在没人消费的 `response_queue.get()` 上。

空 remainder：`LRUPromptCache.fetch_nearest_cache`（`mlx_lm/models/cache.py` 1674–1678）在 `result.exact is not None` 时返回 `(cache, [])`。`_generate` 用 `prompt_cache_count = len(prompt) - len(rest)`（753–756），再把 segment 弹到 `N == 0`（758–764）。精确命中时 `segments` 变成 `[]`，随后调用 `insert_segments(segments=[segments], …)`。`BatchGenerator.insert_segments`（`generate.py` 1607–1648）执行 `seq = list(seq)` 后读 `seq[-1]`（1646）。空列表即 `IndexError: list index out of range`。这里没有“留下一个 token”的保护。concurrency 1 仍然走这条 batch 路径：无 draft、`seed is None` 时 `_is_batchable` 为真；第一轮只创建 `BatchGenerator` 并重新入队，下一轮进入 776 行。`_serve_single` 自己的 `except`（1023–1024）罩不住这条路径。

历史日志 `/tmp/kiln-mlx.err`（mtime 2026-09-25 02:43:27，仍在追加，但不是新崩溃）：`IndexError` 7 次，栈都是 `Exception in thread Thread-1 (_generate)` → `server.py:776` → `generate.py:1646`。最后一次在该文件第 43876 行，前一次 `Starting httpd` 之后；当前这次 `Starting httpd` 在第 43881 行，时间 2026-09-11 19:50:34,791。该行之后 `IndexError` 为 0。与进程启动时间 19:50:33 一致。今天没有新的这类栈。没有 attach，也没有发生成请求，因此不能用这份日志证明生成线程此刻仍活着，只能证明这份代码里的死法还在，且这次启动之后没有再记到一次。

CLI：`kiln/.venv/bin/python -m mlx_lm.server --help` 的 usage 含 `--draft-model DRAFT_MODEL`（源码 1781–1786），不含 `--kv-bits`。`--kv-bits` 只出现在同安装树的 `generate.py` / `cache_prompt.py`，不是这个 server 的参数。现场没有传 `--draft-model`。

架构（`…/qwen3.5-9b-hauhau-aggressive-mxfp4/config.json`）：`architectures = ["Qwen3_5ForConditionalGeneration"]`，`model_type = qwen3_5`。`text_config.model_type = qwen3_5_text`，`full_attention_interval = 4`，`num_hidden_layers = 32`，`layer_types` 为 24 个 `linear_attention` + 8 个 `full_attention`。`mlx_lm/models/qwen3_5.py` 的 `DecoderLayer`（212 行）按这个间隔分流；`TextModel.make_cache`（304–305）对 linear 层用 `ArraysCache`，对 full attention 用 `KVCache`。`vision_config.depth = 27`，权重索引 1010 个 key 里有 `vision_tower` 333 个、`language_model` 677 个。`Model.__init__` 只建 `TextModel`（367–372），`Model.sanitize` 丢弃 `vision_tower` / `model.visual`（384–388），`__call__` 只跑 `language_model`（374–382）。这是带视觉塔检查点的文本 LM，不是生图模型。生图/视频走 Kiln `/generate`（`backend/app/main.py` 880 行附近的 `MediaService`），不经过这只 8081。

聊天只传文本：

- `backend/app/services/chat.py` 556–584 行把将要发送的消息收成 `content` 字符串；`make_req` 1105–1122 行放进 `ChatRequest`。
- 普通流式在 1335 行 `self.provider.stream(req)`。续写才改走原始 prompt，并且为了避开精确缓存命中会丢掉至少一个 token（`backend/app/services/continuation.py` 1–8、16–41 行）。那是续写客户端的回避，不是 server 已修好。
- `MlxProvider._payload`（`mlx.py` 79–84）把 `request.messages` 原样放进 JSON；`stream`（252 行）POST 到 `Settings.mlx_chat_url`（`config.py` 114–118），即 `/v1/chat/completions`。
- mlx-lm `process_message_content`（`server.py` 118–141）只接受字符串或 `type == "text"` 的片段，其它类型直接 `ValueError`。
- OpenAI 兼容入口 `main.py` 932 行的 `openai_chat` 在 1005 / 1059 行调用同一个 provider。946–949 行只是在检查用户文本时把 list 拼成字符串，并不把图片送进 9B。

## proposed change

这次不改。以后若排期重启，再换二进制；热改 site-packages 不会进入已经跑了 13 天的 PID 1581。

1. 健康检查至少要看 `_generation_thread.is_alive()`，死了返回非 200。只看 `is_alive()` 发现不了“线程还在但卡住”。不要靠升级整包 mlx-lm 来顺手做这件事。
2. `insert_segments` 在 segment 被弹空时不要读 `seq[-1]`。上游 PR 1581 的方向是精确命中时留下一个 token。issue 1446 / PR 1581 只是对照，不是本机今天又崩了的证据。未合并进这份 0.31.3。
3. 续写路径已经在丢最后一个 token。普通 `/v1/chat/completions` 仍会整段送出，精确命中仍然危险。不要把续写回避写成漏洞已修复。
4. 不要给这只 9B 加 `--draft-model`（第二份模型，交换区已经很紧）。`--kv-bits` 不是 server CLI，不能靠启动参数打开。

## risk

重启这只进程才会换上补丁。交换区大约 13/14GB，再加载一份 9B 或 draft 模型可能把机器打满。健康检查改成非 200 会让 Kiln 把“生成线程已死”显示成离线，这是想要的结果，但活着却卡死的线程仍会 200。留下一个 token 会改变缓存命中长度。改错成 Homebrew Python 3.14 那棵树，对 PID 1581 没有作用。未重启前，Kiln 仍会把 HTTP 200 显示成在线。

## tests

故障注入：not_done。禁止对 PID 1581 做，这次也没有做。没有向 8081 发 `/v1/chat/completions` 或其它生成请求。

已做的只是静态核对：上述行号、`--help` 文本、config 与权重索引的 key 前缀、日志里 7 次旧栈且当前 `Starting httpd` 之后次数为 0。

以后若要复现，用另一只端口和一只小模型，不要动 PID 1581，也不要再加载这只 9B。预期是精确缓存命中后生成线程退出，而补丁前的 `/health` 仍为 200。这次没有跑。

## rollback

没有补丁可回滚。回滚点就是当前 `server.py` 的 sha256 `cdfcb4ac848636f9927851a0ec7a951584526530cb7832ba58049e4a9144db8b`。将来若替换该文件，用这份 blob 盖回，并用现有 LaunchAgent 脚本重启；不要 `pip install -U`。

## status

代码风险仍在这份 mlx-lm 0.31.3 里。未修复。`.venv` 与 PID 1581 的导入树一致，不标红。故障注入 not_done。2026-09-11 19:50:34 这次启动之后，日志里没有新的 `IndexError`。不要把“今天没再记到崩溃”写成“生成线程已验证健康”或“漏洞已修复”。
