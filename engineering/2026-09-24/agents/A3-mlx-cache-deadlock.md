# A3：MLX prompt cache 与生成线程停滞

只读核对。没有重启服务，没有向 `127.0.0.1:8081` 发任何生成请求，没有下载权重，没有改 Kiln 源码。复现脚本未执行。证据摘录在 `engineering/2026-09-24/raw/A3/evidence.txt`。上游 `main` 快照在 `raw/A3/upstream-main/`，不是本机安装树。

## 结论

本机正在跑的是 **mlx-lm 0.31.3 + mlx 0.32.1**。0.31.3 仍是 GitHub 上的最新 **release**；`main` 比 tag `v0.31.3` 超前 129 个提交，那些修复都 **没有** 装进这个 venv。

已捕获的失败不是 #1834 的原生 `eval_impl` 死锁，也不是 #1256 的 `Stream(gpu, 1)`。它是 exact prompt-cache 命中把 segment 弹空，`insert_segments` 在 `seq[-1]` 上 `IndexError`，**生成线程死亡**。`/private/tmp/kiln-mlx.err` 里这个栈出现了 7 次，全部是 `POST /v1/completions`，时间都在 **2026-09-11 19:50:34 这次进程启动之前**。当前 PID 1581 自那次启动后，本次扫描时 chat access 为 **528 次 200、1 次 404**（最近一条 2026-09-24 21:12:12 仍是 200），**0 次** `/v1/completions`，**0 次** 线程死亡。日志仍在被该进程追加，数字是扫描快照。不能说这个进程现在已经卡死。代码路径还在，下一次 exact 命中仍会打死线程；0.31.3 的 `GET /health` 在那之后继续返回 200。

`feat/conversational-reliability`（`a6a4d2e`，以及 tip `cbbaa6e`）**已经在当前 HEAD 的历史上**。Kiln 的缓解是 Continue 时丢掉最后一个 token，避免 exact 命中。没有 nonce 探针，也没有「推理不健康就 503」的熔断。

## 版本矩阵

| 组件 | 版本 | 路径 / 身份 |
|---|---|---|
| 进程 | PID 1581，PPID 1，2026-09-11 19:50:33 启动 | cwd `/Users/rainhuang/Desktop/models/kiln` |
| 解释器 | CPython 3.12.12（Homebrew） | `/opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python` |
| 包来源 | Kiln venv，不是系统 site-packages | `/Users/rainhuang/Desktop/models/kiln/.venv/lib/python3.12/site-packages` |
| mlx | **0.32.1** | `mlx-0.32.1.dist-info`；PID 映射了 `mlx/core.cpython-312-darwin.so` 和 `mlx/lib/libmlx.dylib` |
| mlx-metal | 0.32.1 | `mlx_metal-0.32.1.dist-info` |
| mlx-lm | **0.31.3** | `mlx_lm-0.31.3.dist-info`；`mlx_lm/_version.py` 为 `"0.31.3"` |
| 模型 | qwen3.5-9b-hauhau-aggressive-mxfp4 | `config.json`：`model_type=qwen3_5`，linear + full attention |
| Kiln git | `ui/account-menu-placement` | `0a4322de9a506b54411af2ed10f8c081e73ba003` |

现场参数（与 `scripts/start-mlx.sh` 一致，和 `docs/inference-mlx.md` 里「未设置 bytes / size 3 / 1G」的旧句子不一致）：

`--decode-concurrency 1 --prompt-concurrency 1 --prefill-step-size 1024 --prompt-cache-size 4 --prompt-cache-bytes 4G --temp 1.0 --top-p 0.95 --top-k 20`

上游 release：mlx-lm 最新 tag 仍是 `v0.31.3`（`ed1fca4cef`）。mlx 最新 release 是 0.32.2（2026-08-25）；本机是 0.32.1（2026-08-18）。

## 已安装 mlx-lm：cache、prefill、生成线程

生成线程在导入时就启动，没有外层 try，线程一死就不会再拉起来：

- `mlx_lm/server.py:451-452`：`Thread(target=self._generate)` 然后 `start()`
- `mlx_lm/server.py:688-692`：`_generate` 里用 **本线程** 的 `mx.default_stream(...)`，不是模块导入时创建的那条 stream
- `mlx_lm/server.py:821-827`：`BatchGenerator(..., prefill_step_size=self.cli_args.prefill_step_size, stream=generation_stream)`。现场 prefill 步长是 **1024**
- CLI 默认值在 `server.py:1865-1880`：prefill 默认 2048，cache 条数默认 10，bytes 默认不设。`BatchGenerator.__init__` 的默认步长也是 `generate.py:1509` 的 2048

Prompt cache 是 token-id 的 trie，不是字符串 key：

- `mlx_lm/models/cache.py:1623` `LRUPromptCache`
- `cache.py:1674-1678` `fetch_nearest_cache`：**exact** 命中时 `deepcopy` 缓存并返回 `rest=[]`
- `cache.py:1680-1688`：更长的条目只有 `can_trim_prompt_cache` 为真才裁后缀。裁的时候还故意留最后一个 token（`prefix = min(len(tokens)-1, common_prefix)`），所以 **更长命中不会走出空 rest**
- `cache.py:1690-1694`：更短前缀，`rest = tokens[len(prefix):]`
- `cache.py:88-92`：`can_trim` 要求每一层 `is_trimmable()`
- `mlx_lm/models/qwen3_5.py:304-305`：`ArraysCache(size=2)`（linear）+ `KVCache`（full）
- `ArraysCache`（`cache.py:594` 起）**没有** `is_trimmable`，继承 `_BaseCache.is_trimmable` → `cache.py:146-147` 返回 `False`。这条模型 **不能 trim**。多轮 chat 只能吃 segment 边界上的更短前缀（system / user），不能把「上一轮 prompt+生成」裁成当前 prompt

Exact 命中如何打死线程（batch 路径；`seed is None` 且无 draft，所以 concurrency=1 仍然走 `BatchGenerator`）：

- `server.py:561-563`：`/v1/completions` 整段 prompt 是 **一个** segment
- `server.py:753-764`：`N = len(prompt)-len(rest)`。exact 时 `rest=[]`，`N` 等于整段长度，`segments.pop(0)` 把列表弹空
- `server.py:776-784`：`insert_segments(segments=[segments])` **不在** 上面 tokenize 的 `try` 里
- `generate.py:1645-1646`：`seq` 为空时 `seq[-1]` → `IndexError: list index out of range`
- 异常冒出 `_generate`，线程结束。HTTP 线程堵在 `response_queue.get()`（`server.py:1048`）。`handle_health_check`（`server.py:1633-1641`）不看线程，固定 `{"status":"ok"}` 200

Chat 的 segment 切分在 `server.py:530-624`（system / user / thinking tail）。segment 结束且还没到 prompt 末尾时，`server.py:864-879` 把前缀写进 trie。生成结束时 `server.py:903-908` 用 `r.all_tokens`（prompt token + 生成 token，见 `generate.py:1443`）写一条 `assistant` 缓存。所以 **把上一轮完整 token 序列原样再送**（Continue 的 `/v1/completions`）才会 exact；普通「同一句 user 再说一遍」通常只是更长 key 的前缀，hybrid 模型 trim 不了，退回到更短的 system/user 快照，不会把 segment 弹空。

## 两个 issue，以及安装版里有没有修复

### #1256（仍 open，2026-05-07）

`mlx_lm.server` 在 worker 线程里 `mx.eval` 报 `There is no Stream(gpu, 1) in current thread`。原文绑在 `RotatingKVCache` / 滑窗（Gemma 4）。评论说 vllm-mlx 的 worker 上，非滑窗模型也会中同一条「导入线程创建的 `generation_stream`」。

和本安装的关系：

- tag `v0.31.3` 含 PR **#1090**（`mx.new_thread_local_stream`，`generate.py:226`）。issue 认为这只换了 stream id，没修「stream 绑在导入线程」。
- 结构性修法 PR **#1088**、**#1182** 关闭但 **未合并**。
- `main` 上后来有 **#1775**（2026-08-26，decode 循环包进 stream）和 **#1840**（2026-09-04，server 把同一条 stream 传给 `stream_generate`）。**都不在 0.31.3。**
- 本安装的 **server batch 路径**已经在 `_generate` 线程里取 `default_stream` 再交给 `BatchGenerator`（`server.py:692`、`826`；`generate.py:1854` 的 `with mx.stream(self._stream)`）。这和 issue 里「用模块级 stream」的 traceback 不是同一条路径。
- 现场模型不是 `RotatingKVCache`。整份 `kiln-mlx.err` 里 **没有** `There is no Stream`。

因此：安装版 **没有** #1256 在 `main` 上的后续补丁；但现有日志和这条 server 路径 **不能** 把现场故障判成 #1256。

### #1834（仍 open，2026-09-03，无评论、timeline 长度 0）

cache 打满后，并发 + 中途断开，生成停在 `mlx::core::eval_impl` 的 `condition_variable::wait`。没有 Python 异常。`GET /v1/models` 仍 200。报告环境是 mlx-lm **0.31.3**、mlx 0.32.0（以及更早的 0.31.2）；作者写明 0.31.2→0.32.0 **不能** 消除。没有关联 PR。mlx 0.32.1 / 0.32.2 的 release note 里没有这条死锁。issue 写在 0.32.2 发布之后，到本次拉取仍 open。

安装版 mlx-lm **就是** 报告里的 0.31.3，server 侧 cache 淘汰逻辑没有后继修复。mlx 是 0.32.1，比「已证明修不好」的 0.32.0 新一个小版本，比 0.32.2 旧，**没有证据**说 0.32.1 修了它。

不能把现场说成已经发生 #1834：日志里没有原生栈；最近一次 cache 统计是 **4/4 条、0.23 GB**（条数满，离 4G 很远）；`prompt-concurrency 1`。作者的复现是 6 路并发、全新大前缀、一半客户端 2 秒断开，cache 16 条 / 约 27 GB。降低并发到 2 **没有** 让他们复现消失，所以 concurrency=1 也不是证明。只是本机没有抓到。

### 相邻、但不是这次日志里的死法

- **#1472**（2026-09-04 在 `main` 关闭）：batch 里有的请求带 logits processor、有的不带，`TypeError` 打死线程。安装版没有该修复。本日志的死法是 `IndexError`，不是这个。
- **#1791**（2026-09-05）和 **#1837**（2026-09-11）：线程死后 `/health` 改 503，`generate()` 不再永久阻塞。**不在 0.31.3。** 今天拉的 `main` 里，exact 命中仍会把 segment 弹空；`insert_segments` 改成抛 `ValueError: Sequence N has an empty prompt.`（快照 `generate.py:1667-1669`），调用点仍在 tokenize 的 `try` 之外（`server.py:742`）。根因在 `main` 上也还在，只是死后健康检查会变 503，而不是继续 200。

## Kiln 本分支（HEAD 已包含 a6a4d2e / cbbaa6e）

`git merge-base HEAD feat/conversational-reliability` = `cbbaa6e`。`a6a4d2e` 是 HEAD 的祖先。推理缓解 **在这个分支上**，不是只活在另一条未合并的分支里。

Cache key（Kiln 侧，不是 MLX trie）：

- Continue 把已经发出去的 completion 字符串记在会话 `settings_json.continue_completion_prompts`，最多 16 条。`chat.py:482-499`
- `tokens.py:91-117` `continuation_completion_prompt` → `continuation.py:16-41` `shorten_until_unused`：至少丢掉 1 个 token；若该字符串已用过，继续丢，直到 `min_keep=8`
- 原因写在 `continuation.py:3-8` 和 `26-27`：0.31.3 在 exact 命中时清空 `insert_segments` 并杀死生成线程。丢掉最后一个 token 是为了避开 **token 序列与 trie key 完全相同**。Qwen3.5 不能 trim，所以这条更长的 assistant 缓存也用不上，Continue 会几乎整段重 prefill，这是用 miss 换不死
- 缩短耗尽后仍会返回一个已经用过的字符串（`while` 条件失败就返回）。那一次仍可能 exact。changelog 也写了：「残留的 exact 命中仍可杀死生成线程」
- 普通 chat **不** 走这条缩短。`providers/mlx.py:239-253` 只有 `extra.raw_prompt` 才打 `/v1/completions`

健康检查 **不是** 生成探针：

- `providers/mlx.py:57-63`：`GET` `settings.mlx_health_url()`，200 即健康
- `config.py:120-124`：`http://127.0.0.1:8081/health`。这是 mlx 的空 200，不跑 1 token
- 全仓库 `backend/` **没有** `nonce`。`feat/conversational-reliability` 上也没有

所谓熔断，不是 503 断路器：

- `chat.py:314-328`：连续超时 `_timeouts` 加到 3，`inference_status().ready` 变 false。进程内计数，重启 API 即清零（`chat.py:67`）
- `main.py:295-329`：`/health` 在 MLX HTTP 仍通、但 `ready=false` 时返回 `"status": "degraded"`，`provider.reachable` 仍可为 true。测试 `backend/tests/test_inference_watch.py:1-15` 锁的就是这个
- 超时来自 `chat.py:1367-1374`（`TimeoutError` / `ConnectionError`），以及 Continue 无输出的 transport 中断（`1383-1391`）。`mlx_timeout_s` 默认 600（`config.py:25`）。线程死后，Kiln 要等到这次超时才记一笔，**不会** 因此拒绝下一次 chat
- chat 硬失败返回的是 **502**（或上下文 413），见 `chat.py:1438-1462`。不是 503
- 本分支的 503 是别的事：账号未就绪（`main.py:360`、`407`）、Hub 目录/下载（`531`、`553`）、视频把 chat park 掉（`655-658`）、compiler 不可用（`862`）
- `generation_concurrency` 默认 1（`config.py:78`）。Kiln 自己不会把多路 chat 同时打进 MLX。打满 cache 的并发要来自别的客户端，或 Kiln 之外的脚本

`cached_tokens` 只是把 mlx 的 `usage.prompt_tokens_details.cached_tokens` 读出来（`providers/mlx.py:125-133`）。那是 `len(prompt)-len(rest)`（`server.py:756`、`1344-1346`），不是 Kiln 自己的 cache key。

## 现场是不是已经中招

| 说法 | 证据 |
|---|---|
| 这台机器的 mlx-lm **曾经** 被 exact 命中打死生成线程 | 有。7 次栈与当前安装文件行号一致，都在 `/v1/completions`，2026-09-11 14:55–19:50:01。每次之后 `/health` 仍 200，然后进程被拉起 |
| **当前** PID 1581 的生成线程已经死了 | **没有这条证据**。启动日志 19:50:34 之后 0 次 IndexError、0 次 completions；扫描时 chat 为 528×200 + 1×404，最近 2026-09-24 21:12:12 仍 200 |
| 当前代码下一次 exact `/v1/completions` 仍会打死线程，且 `/health` 仍 200 | 有。安装源码未变；`main` 的 503 健康检查不在这个包里 |
| #1256 正在发生 | 没有。日志无 `Stream(gpu)`；模型 cache 类型也不匹配 issue 的滑窗触发条件 |
| #1834 正在发生 | 没有抓到。cache 0.23 GB / 上限 4 GB，concurrency 1。不能反过来说装上去的代码已免疫 |

09-11 晚上那几枪和 `cbbaa6e`（17:36 写入缩短逻辑）之后的时间重叠，而且走的是 mlx 的 `/v1/completions`，不是 Kiln 缩短之后的字符串。更像直接打 MLX 的探针/benchmark，不是「缩短逻辑没进这个 HEAD」。当前进程起来之后 Kiln 没有再打 completions。

## 还缺什么

- 没有对 PID 1581 做 `sample`。#1834 只能靠原生栈确认，这次故意没采样，避免停到现场 GPU 线程。
- 没有在 **这个** 进程里复现 exact 命中。历史栈证明的是同一份安装文件，不是「1581 此刻已死」。
- 不知道 09-11 之后 Kiln Continue 是否真的一直避开了 exact（这段时间 completions 计数是 0）。缩短逻辑在单测里（`backend/tests/test_continuation.py`），没有新的现场反例。
- mlx 0.32.2 未安装。#1834 在它发布之后仍 open，但不能代替一次对照实验。
- `main` 的 503 健康检查能否在 exact 命中后让 Kiln 的 `provider.health()` 变 false，要换包之后才知道。换包不在本次范围。

## 给编排者的实验（你拿着 GPU 锁再跑）

脚本：`engineering/2026-09-24/scripts/repro_prompt_cache.py`。未执行。未设置 `KILN_ALLOW_REPRO`。不设这个变量时函数立刻返回 0，不发请求。

它会打到 `KILN_REPRO_URL`（默认就是 `http://127.0.0.1:8081`，也就是 PID 1581）。exact 阶段 **会杀死当前生成线程**。0.31.3 不会自己恢复。跑之前接受「跑完必须由你重启 LaunchAgent」，不要和别的 benchmark 重叠。

建议顺序：

1. 记下 PID、`/health`、以及 `kiln-mlx.err` 的当前大小。确认没有别人在打 8081。
2. `KILN_ALLOW_REPRO=1 python3 engineering/2026-09-24/scripts/repro_prompt_cache.py`
   - **hit/miss**：同一条全新 system、两个不同 user，对一个全新 system。期望第二条 `cached_tokens > 0` 且小于 `prompt_tokens`（system 段前缀）；新 system 为 0。若第二条等于 `prompt_tokens`，那是 exact，不该出现在这个 chat 形状里。
   - **hung stream**：本地 tokenizer（`local_files_only`）把 `encode(prompt)+logprobs 里的 completion id` 解回字符串，再 `stream` 打 `/v1/completions`。期望 replay 和随后的 1-token probe 都在 `KILN_REPRO_HANG_TIMEOUT_S`（默认 20s）内超时，而 `GET /health` 仍是 200。同时 err 日志应新增与历史相同的 `generate.py:1646` `IndexError`。
3. 看到签名后再重启 MLX。不要在线程已死时继续把 Kiln 的 600s 超时请求堆上去。
4. **不要**在这台 24GB、正在服务的进程上做 #1834 那种「6 路大 schema + 半路断开 + 把 4 条 / 4GB cache 打满」。那是另一项实验：需要维护窗口、独立进程或可丢弃的 server，并且事先接受 unified memory 被 KV 占满。concurrency=1 可能让它根本不出现，出现了也只会表现为无 Python 异常的永久卡住，`/health` 依旧 200。判据是 `sample` 里主生成线程停在 `mlx::core::eval_impl` → `condition_variable::wait`，而不是又一个 `IndexError`。
5. 若要验证「换 `main` 是否只改善可观测性」：exact 命中在今天的 `main` 上仍会杀线程，但 `/health` 应变成 503，而不是 200。那次升级会换掉 PID 1581 加载的包，单独排期。

脚本只打印 JSON 事件（`cache_hit_miss`、`exact_hit_hang`）。`installed_0_31_3_signature == true` 表示：replay 挂、probe 挂、health 仍 200。
