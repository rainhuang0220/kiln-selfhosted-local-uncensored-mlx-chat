# Kiln 系统基线（2026-09-24）

总控在只读调查和一次受控生成探针之后写下这份审计。子 Agent 的专项报告在 `agents/`。数字都来自本机命令，不沿用历史笔记。

## 机器

MacBook Pro（Mac16,1），Apple M4，10 CPU（4P+6E），10 核 GPU，Metal 4。统一内存 `hw.memsize = 25769803776`（24 GiB），可用 `hw.memsize_usable = 24904433664`。macOS 26.5（25F71），内核 `xnu-12377.121.6~2 / RELEASE_ARM64_T8132`。开机已约 116 天。

20:56 CST 采样（A1）：

| 项 | 值 |
| --- | --- |
| jetsam `kern.memorystatus_level` | 37 |
| `kern.memorystatus_vm_pressure_level` | 2（xnu：Urgent，不是 Critical） |
| free pages | 约 72 MiB |
| compressor 占用 / 存下的逻辑量 | 约 11.0 GiB / 46.7 GiB |
| swap | 15300 MiB / 16384 MiB |
| 5 秒内 swap used | 不变（当时没有新的换出） |

没有温度或热降频读数。`machdep.xcpm.*` 不存在，`sudo -n powermetrics` 要密码。不能声称正在热降频。

磁盘：`/System/Volumes/Data` 926 GiB，已用约 476 GiB，可用约 403 GiB。空间不是当前瓶颈。

## 生产进程

`com.kiln.mlx` 处于 running。PID **1581**，已运行约 13 天。工作目录是 Kiln 仓库。监听 **127.0.0.1:8081**。

启动脚本 `~/Library/Application Support/kiln/start-mlx.sh` 与进程参数一致：

```text
.venv/bin/python -m mlx_lm.server
  --model /Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4
  --host 127.0.0.1 --port 8081
  --max-tokens 32768
  --temp 1.0 --top-p 0.95 --top-k 20
  --decode-concurrency 1 --prompt-concurrency 1
  --prefill-step-size 1024
  --prompt-cache-size 4 --prompt-cache-bytes 4G
  --chat-template-args {"enable_thinking":false,"reasoning_effort":"medium"}
```

`.venv/bin/python` 是指向 Homebrew Python 3.12.12 的符号链接，但 `sys.prefix` 是 Kiln venv。`ps` 里看到的是解析后的 Homebrew 路径，不是另一套解释器。

`footprint -p 1581`：常驻约 **5086 MB**，其中 IOAccelerator（GPU）约 4872 MB。峰值 **7944 MB**。`ps` RSS 只有几十 MB，不能用来判断模型是否加载。权重目录 `du -sh` 为 **5.3G**。

同机端口：

| 端口 | 进程 | 说明 |
| --- | --- | --- |
| 127.0.0.1:8081 | Python 1581 | MLX，仅本机 |
| 127.0.0.1:8787 | Python 15068 | Kiln API（uvicorn） |
| 127.0.0.1:7777 | node 97771 | Kiln web |
| 198.18.0.1:7777 | ClashX | Fake-IP 网段，和 web 不是同一个地址 |

## 软件版本（Kiln venv，也就是正在服务的那一套）

| 包 | 版本 |
| --- | --- |
| Python | 3.12.12 |
| mlx / mlx-metal | 0.32.1 |
| mlx-lm | **0.31.3**（PyPI 最新 release 仍是 2026-04-22 的 v0.31.3） |
| transformers | 5.15.1 |
| tokenizers | 0.22.2 |
| huggingface_hub | 1.28.0 |
| torch | 未安装 |

`/opt/homebrew/bin/mlx_lm` 走 Python 3.14，A1 记录它因 OpenMP Error #15 退出。生产不要改用这支。

Git：`/Users/rainhuang/Desktop/models/kiln`，分支 `ui/account-menu-placement`，HEAD `0a4322d`。`cbbaa6e`（2026-09-11，`fix(chat): harden continuation and long-dialogue cache for RC2`）和 `a6a4d2e` 都是 HEAD 的祖先。调查开始时工作区是干净的；本目录 `engineering/2026-09-24/` 是这次新增的。

## 模型

目录名对应 README 里的 `TheCluster` mxfp4 量化，基座 `HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive`。README 写「0/465 refusals」。这是作者声明，不是本机测量。

`config.json`：

- `model_type = qwen3_5`，`Qwen3_5ForConditionalGeneration`（带 vision/video 配置，文本走 `text_config`）
- 量化 `mxfp4`，group 32，4 bit
- 文本 32 层，`full_attention_interval = 4`（每 4 层里 3 层 `linear_attention`，1 层 full attention）
- full attention：`num_key_value_heads = 4`，`head_dim = 256`，`hidden_size = 4096`
- `max_position_embeddings = 262144`，tokenizer `model_max_length = 262144`
- `eos_token = <|im_end|>`，`eos_token_id = 248044`，`vocab_size = 248320`

KV 粗算只计 8 层 full attention、fp16 K+V：`8 * 2 * 4 * 256 * 2 = 32 KiB/token`。20k token 约 640 MiB，32k 约 1 GiB，262k 约 8 GiB，再加 5.3 GiB 权重和 prefill 激活。262k 不是这台 24 GiB 机器上的可部署长度。线性注意力层的状态是另一笔账，还没实测。

## Tokenizer：字符和 token 不是一回事

用模型目录里的 `tokenizer.json`（`tokenizers.Tokenizer`，不加 chat template）：

| 文本 | 字符 | token | 耗时 |
| --- | ---: | ---: | ---: |
| 编号事实混合中文，正好 20000 字 | 20000 | **13464** | 8.2 ms |
| `"测" * 20000` | 20000 | **20000** | 9 ms |

变长中文大约 1.49 字/token。单字重复是 1 字/token。英文探针 `item{i} value…` 大约 2.4 字符/token。原始记录：`raw/orchestrator/tokenizer_counts.json`。

Chat template 还会再加角色和特殊 token。下面的服务日志才是模型真正吃进去的 prompt token 数。

## 请求链路（本机已看到的部分）

```text
浏览器
  → Kiln web  127.0.0.1:7777（node）
  → Kiln API  127.0.0.1:8787（uvicorn，/health 会藏起内部 base_url：private 模式）
  → MLX       127.0.0.1:8081
公网 kiln.plainlist.space → VPS Caddy/API → SSH 反向隧道 → 上述本机端口
```

VPS 和 Caddy 的超时不在这台 Mac 的进程表里，标为未在本机观察到。ClashX 在 `198.18.0.1:7777`，和 Kiln web 的 `127.0.0.1:7777` 不是同一个套接字。

Kiln API `GET /health`（2026-09-24 20:59 CST）返回 `status=ok`，`inference.ready=true`，`consecutive_timeouts=0`，`chat.state=running`，`context_window=262144`，`practical_prompt_budget=32768`，`default_max_tokens=1536`，`enable_thinking=false`。

## 五种故障，各自的证据

1. **进程不存在或反复重启。** 不成立。PID 1581 连续运行约 13 天，`launchctl` state=running。`runs=6` 只说明 116 天开机期间曾经拉起过多次，不是现在在重启循环。
2. **进程在，但模型没加载完。** 不成立。GPU footprint 约 4.9 GiB，短提示能生成并 `finish_reason=stop`。
3. **健康接口活着，生成线程已经死。** **现在不成立**（探针生成成功）。**检测缺口成立**：安装的 mlx-lm 0.31.3 里 `handle_health_check` 无条件写 `{"status":"ok"}` 和 HTTP 200。上游 main 的 #1791（2026-09-05 已合并）会在生成线程退出时返回 503，这份安装没有。Kiln API 的 `inference.ready` 只在连续 3 次超时之后变 false，空闲时不会发现死线程。
4. **本机推理正常，VPS 或前端超时。** 本机短提示在热状态下 0.3–0.8 秒完成。公网超时这一跳还没有对照测量。
5. **模型输出正确，传输或前端组装错误。** 这次直连 MLX 的短提示，客户端拼出来的文本就是 `pong-kiln-baseline` / `pong-warm1`，没有缺字。前端和隧道不在这条探针里。

## 已实测的短提示延迟

直连 `127.0.0.1:8081`，`stream=true`，`temperature=0`，`max_tokens` 16 或 32。服务日志里的 prompt 进度是服务器 token 数。

| 次序 | 客户端 TTFT | 总时间 | 输出 | 服务器进度 |
| --- | ---: | ---: | --- | --- |
| 13 天空闲后的第一发 | 24.01 s | 24.30 s | `pong-kiln-baseline` | 28/28，约 24 s |
| 紧接着 warm1 | 0.608 s | 0.806 s | `pong-warm1` | 20/20 |
| warm2 | 0.404 s | 0.602 s | `pong-warm2` | 20/20 |
| 重复 warm1 | 0.293 s | 0.482 s | `pong-warm1` | **4/4**（前缀缓存命中，剩下 4 个 token） |

第一发的 24 秒不能当成稳态 TTFT。采样时 load average 约 3.5，内存压力 Urgent，15 个只读 Agent 同时在跑。热状态的重复前缀把 prefill 收到 4 个 token，而且没有把生成线程打挂。

缓存日志：Prompt Cache 保持 4 条序列、约 0.21–0.23 GB，和 `--prompt-cache-size 4` 一致。

原始文件：`raw/orchestrator/probe_short.json`，`probe_warm.json`。

## Prompt cache 死锁：代码里有，这次没复现

mlx-lm 0.31.3 的 `ResponseGenerator` 在精确缓存命中时会把 `segments` 弹空，随后 `insert_segments` 对空列表取 `seq[-1]`（`generate.py` 约 1644 行）。Kiln `continuation.py` 用「丢掉最后一个 token」避开这条路径，注释写明 0.31.3 会在精确命中时杀掉生成线程。

上游 PR #1581（`_fetch_prompt_cache`，命中后强制留下 1 个 token）**没有合并**。Issue #1215 已关闭。Issue #1834（缓存满且并发时 `eval_impl` 死锁）和 #1256（sliding-window 的 Stream 线程错误）截至 2026-09-24 仍是 open。main 上 2026-09-11 还有 #1837（模型切换泄漏和死生成线程），不在 0.31.3 tag 里。

这次重复同一句时服务器处理了 4/4，不是 0 个剩余 token，所以没有踩中空 `segments`。不能因此说生产路径永远不会踩中。Qwen3.5 的混合缓存（linear attention）是否允许 trim，要单独做实验。

## 长输入在 Kiln API 里会不会被悄悄裁掉

`practical_prompt_budget` 默认 **32768**（注释写明这是 prompt 预算，不要再减 `max_tokens`）。`context_window` 仍是 262144。

`truncate_messages` 只丢最老的轮次，不丢 system，也不丢最新一条 user。最新 user 若仍超过剩余预算，`pack_user_message` 会改写送进模型的正文。用户原文在这之前已经 `_insert_message` 进数据库，所以库里可恢复，但模型看到的不是原文。`overflow_policy` 默认 `truncate_oldest`。只有把它改成 `error` 且 `prompt + max_tokens > 262144` 时才会拒绝。32768 这个真正的闸门不会走那个 error 分支。

20000 个变长中文字符约 13464 token，20000 token 也低于 32768，单条消息按现有估计不该触发打包。超过 32768 token 的单条原文会在模型侧被打包，接口仍可能显示成功。这是产品缺口，还没改代码。

## 这份审计之后已经量到的

长上下文、缓存和清理写在同目录的 `performance-baseline.md`、`disk-inventory-and-cleanup.md`。这里只补请求链路。

绕过 Clash 假 IP 之后，`curl --resolve kiln.plainlist.space:443:175.24.134.228`：

- `GET /` → HTTP 200，`server: nginx`，约 0.43 s，页面标题 Kiln — local Qwen。Last-Modified 2026-09-15。
- `POST /chat` 不带登录 → HTTP 401，JSON `auth_required`，约 0.74 s。这是 Kiln API 的正文，说明 nginx → 隧道 → 本机 8787 是通的。没有登录，所以没有发生成。
- `GET /health` → nginx 404。公网 vhost 没有把 `/health` 反代进来。本机 8787 和 8081 的 `/health` 仍然 200。

两条 SSH 反向隧道同时在：`17777→127.0.0.1:8787`（公网 API）和 `8081→127.0.0.1:8081`（VPS 本机上的 MLX，README 的公网页不走它）。VPS 上 8081 是否只绑环回，从这台 Mac 看不到。

## 还没做

- llama.cpp 对照。本机没有 GGUF，也没有 `llama-cli`。现网 9B 占着统一内存，没有再加载第二份大模型。
- 把 mlx-lm 换成 main 上未发布的 `/health` 503。那要换掉 PID 1581，这次没有换。
- 64k token。32k 已经到 footprint 8.2 GiB、jetsam 23。
- 拒答率。卡片上的 0/465 仍然只是作者声明。
