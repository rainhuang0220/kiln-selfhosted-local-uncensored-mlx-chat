# A4 推理性能测量协议

日期：2026-09-24。本波只交付协议和客户端，没有跑模型，没有向 `127.0.0.1:8081` 发请求，没有设置 `KILN_ALLOW_BENCH`，没有加载权重，也没有改 `kiln/benchmarks`。

客户端：`kiln/engineering/2026-09-24/scripts/bench_chat.py`。只使用 Python 标准库（`urllib`）。路由核对笔记：`kiln/engineering/2026-09-24/raw/A4/tokenize-routes.txt`。

编排者以后把 JSONL 和 stdout 摘要写到 `kiln/engineering/2026-09-24/raw/A4/`。不要写进 `kiln/benchmarks`；脚本会拒绝。

## 1. 测什么

测已经在跑的 `mlx_lm.server` 的 `POST /v1/chat/completions`（OpenAI SSE）。默认 origin 是 `http://127.0.0.1:8081`。

不测这些东西：

- Kiln `:8787` 的 `POST /chat`。那条链路有 BFF、具名 SSE（`meta` / `snapshot` / `delta` / `usage` / `done`）和会话折叠。`benchmarks/dialogue_reliability/` 打的是这条，不能和本协议的 TTFT 直接比。
- 历史 27B 数字。`BENCHMARK.md` 和 `benchmarks/live/mlx_lm_now.json` 是另一颗模型、另一组服务端 flags。只借用指标定义，不借用 tok/s。
- 公网 `kiln.plainlist.space`。
- 服务端并行扩展。现场 `decode-concurrency=1` 且 `prompt-concurrency=1`。客户端并发 2 测的是排队，不是两路同时预填。

本波读过、但没有改的参照：`benchmarks/run_inference.py`、`benchmarks/dialogue_reliability/`（尤其 `run_baseline.py`、`run_context.py`、`run_prompt_cache.py`、`run_prefill_cold.py`）、`BENCHMARK.md`。

## 2. 开跑前核对现场进程

下面是 2026-09-24 本波 `ps -p 1581` 的只读结果。开跑前再 `ps` 一次。不一致就先记下来，不要改正在服务的进程，也不要重启，除非这一格明确要求进程冷启动。

- 模型：`/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4`
- 监听：`127.0.0.1:8081`，PID 1581
- `--max-tokens 32768`（这是服务端默认上限；客户端必须自己带小的 `max_tokens`）
- `--temp 1.0 --top-p 0.95 --top-k 20`
- `--decode-concurrency 1 --prompt-concurrency 1`
- `--prefill-step-size 1024`
- `--prompt-cache-size 4 --prompt-cache-bytes 4G`
- `--chat-template-args {"enable_thinking":false,"reasoning_effort":"medium"}`
- 进程映射了 `kiln/.venv` 里的 mlx。`mlx-lm` 是 0.31.3。

`scripts/start-mlx.sh` 里写的是 `--temp 0.6`，和现场 argv 的 `1.0` 不同。其余 cache / prefill / thinking 开关一致。请求体按现场 `1.0` 钉死，会覆盖 CLI。矩阵期间不要把采样或 `chat_template_kwargs` 改成别的值，否则前缀缓存键会变。

`lsof` 看不到常驻的 `server.py`（纯 Python 源码不一定保持映射）。路由以 venv 这份 `mlx_lm/server.py` 为准；Homebrew 那份也是 0.31.3，POST/GET 路由相同。

UI 正在生成时不要开矩阵。这台机器只有一个 Metal 服务，另一路请求会排队并改 LRU。

## 3. Token 计数：没有 HTTP tokenize

两边都没有 tokenize 端点。

`mlx_lm.server` 0.31.3 实际路由：

| 方法 | 路径 |
|---|---|
| POST | `/v1/completions` |
| POST | `/v1/chat/completions` |
| POST | `/chat/completions` |
| GET | `/v1/models` |
| GET | `/health` |

`ResponseGenerator._tokenize` 是进程内方法，不是 HTTP。其它路径 404。

Kiln `backend/app/main.py` 也没有 `/tokenize` 或 `/v1/tokenize`。`POST /v1/chat/completions` 是会生成的 BFF，不能拿来计数。

脚本里 `TOKENIZE_HTTP_PATHS` 是空元组。`--count-tokens` 不探测候选 URL，避免对 8081 发 404 或误触生成。它也不下载 tokenizer。

环境变量未设置时，`--count-tokens` 和其他模式一样先被门禁挡住，退出码 2。放行之后它只打印说明，退出码 3，仍然不打开 socket。协议已经包含全部说明，可以不跑这个模式。

本地计数（权重路径确定之后，生成矩阵之前）：

1. 以现场 argv 的 `--model` 目录为准。本波看到的是上面的 9B 目录。目录里必须已有 `tokenizer.json`。没有就停，不要从 Hub 下载，不要 `mlx_lm.load`。
2. 只用已经装在机器上的库读这个文件，例如 kiln venv 里的 `tokenizers.Tokenizer.from_file`。这是计数，不是加载模型。
3. 先数短样本：英文单元 `tok `、标头 `bench-len-00032\n`、以及 `--prompt-tokens 32` 的完整 user 文本。再数 `apply_chat_template` 之后的整段（`enable_thinking=false`，`reasoning_effort=medium`，`add_generation_prompt=true`）。
4. 放行之后用脚本打一发校准（下一节的第 0 格），把 `usage.prompt_tokens` 和本地模板计数对上。对不上就停，不要按比例放大。
5. 权威的 prompt 长度是服务端 `usage.prompt_tokens`。它包含聊天模板，不等于 user 文本的 token 数，更不等于 `--prompt-tokens` 那个重复次数。

禁止 `len(text)//4`。旧的 `benchmarks/dialogue_reliability/runs/context-cold-warm.json`（2026-09-11，Kiln `/chat`，不是本客户端）已经对不上：目标 200 / 2000 / 8000 / 16000 字符，对应 `prompt_tokens` 187 / 1595 / 6291 / 12552。那是汉字填充经过 BFF 的结果，只说明「字符不是 token」，不能拿 0.78 去乘 20000。汉字档也必须单独用 tokenizer 数，再和那一格的 `usage.prompt_tokens` 对账。

## 4. 客户端契约

未设置 `KILN_ALLOW_BENCH=1` 时退出码 2，不访问网络。脚本不会自己设置这个变量。编排者还要先放好 `engineering/2026-09-24/ALLOW_BENCH`；脚本不读这个文件，两道门都要有。不要把变量写进 shell 配置。

退出码：0 全部行没有 `error`；1 至少一行失败；2 门禁、参数、危险 `--model`、输出路径落在 `kiln/benchmarks`、或 `cold` 且并发大于 1；3 是放行后的 `--count-tokens`。

`--model` 只用 `default_model`。别的字符串若不是已存在的本地目录，mlx 会把它交给 `ModelProvider.load`，可能下载或换掉已加载权重。即使目录存在，只要和现场 argv 不是同一个路径，也会触发换权重。矩阵固定 `default_model`。

请求钉死为：`temperature=1.0`，`top_p=0.95`，`top_k=20`，`stream=true`，`stream_options.include_usage=true`，`chat_template_kwargs.enable_thinking=false`，`reasoning_effort=medium`。`max_tokens` 默认 32，避免吃到服务端 32768。超时默认 600 秒，是单次 socket 阻塞上限，不是整段生成的墙钟预算。读块 256 字节。看到 `data: [DONE]` 就停止读，避免 HTTP keep-alive 把 `total_s` / `decode_s` 拖到超时。

每次运行覆盖 `--out`。并发大于 1 时行序是完成序，用 `run_index`，不要用文件顺序。stdout 是汇总 JSON，stderr 是每行简报。分开重定向。

```bash
cd /Users/rainhuang/Desktop/models/kiln
# 仅在 ALLOW_BENCH 已存在、并且这一格允许打 8081 之后：
export KILN_ALLOW_BENCH=1
python3 engineering/2026-09-24/scripts/bench_chat.py \
  --base-url http://127.0.0.1:8081 \
  --model default_model \
  --prompt-tokens 1000 \
  --max-tokens 32 \
  --runs 3 \
  --prefix-mode identical \
  --concurrency 1 \
  --sample-memory \
  --out engineering/2026-09-24/raw/A4/L1000-identical.jsonl \
  > engineering/2026-09-24/raw/A4/L1000-identical.summary.json \
  2> engineering/2026-09-24/raw/A4/L1000-identical.brief.jsonl
```

汉字档把 `--prompt-tokens` 换成 `--chars 20000`。三者互斥：`--prompt-tokens`、`--prompt-file`、`--chars`。

事后只重算汇总、不再打服务器：import 这个模块并调用 `load_jsonl` 与 `summarize`。import 不会跑 `main`，也不需要环境变量。

### 4.1 prompt 怎么造

英文：`bench-len-{N:05d}\n` 加上 `tok ` 重复 N 次。N 就是 `--prompt-tokens`。标头是额外字符，所以 user 文本比 N 次重复更长。`requested_prompt_tokens` 不是 token 数。

定宽标头是为了让阶梯之间不要形成前缀。`bench-len-01000` 不是 `bench-len-04000` 或 `bench-len-10000` 的字节前缀；分叉点在换行之前，后面的 `tok ` 填充不会接在短 prompt 的缓存后面。

汉字：正好 `--chars` 个汉字（Unicode 统一表意文字，含扩展 A 与兼容区；矩阵用 20000）。长度标头是 8 个汉字，表示 8 位补零的长度，编在这 20000 字里面，不是另加。20000 的标头是 `甲甲甲丙甲甲甲甲`（`00020000`，字母表 `甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳` 对应 `0-9a-f`）。其余字来自循环单元「雨停之后旧书店的灯还亮着钥匙仍在抽屉第二层约定没有改期今晚八点送到门口」。`cjk_chars` 必须等于 20000，并且每个字符都是汉字。

`--prompt-file` 不做长度标头。文件内容若一个是另一个的前缀，缓存会命中。矩阵不用这个参数。

JSONL 不保存 prompt 正文。用 `prompt_sha256`、`length_header`、`filler_repeats`、`nonce`、`sizing` 重建。`identical` 的 nonce 为空，同一次参数下正文稳定。

### 4.2 四种前缀

| 模式 | user 文本 | 脚本能不能证明进程冷 |
|---|---|---|
| `identical` | 每次相同，无 nonce | 否 |
| `partial` | 稳定正文加尾部 nonce。汉字档是结尾 32 个汉字换成 nonce，总字数不变 | 否 |
| `fresh` | nonce 放在最前。汉字档替换开头 32 个汉字，总字数仍是 20000 | 否 |
| `cold` | 构造与 `fresh` 相同，只是模式名不同 | 否。进程冷启动只由编排者重启之后、且中间没有别的请求来保证 |

`shared_prefix_chars` 是相对该长度 `identical` 正文的字符前缀，不是 token。token 级命中只看 `cached_tokens`。

nonce 形如 `{run_index:04x}{uuid4}`。`fresh` / `partial` / `cold` 每次不同，所以整个脚本重跑也不会复用上一次的 nonce。`identical` 会复用，这是故意的。

`cold` 且 `--concurrency>1` 直接拒绝。

混合模型的 `ArraysCache` 不能把更长的缓存 trim 成更短的前缀。所以同一长度内必须先 `identical`，再 `partial`：先存较短正文，partial 才能沿用。`fresh` 放最后，因为它会占 LRU。现场 `--prompt-cache-size 4`，fresh 之后不要假设 identical 那条还在。不要在 fresh 后面再补一发 identical 来「确认缓存还在」。

## 5. 指标

时钟是客户端 `perf_counter`，从调用 `urlopen` 之前起算。`request_start_unix` 只用于对齐日志。

| 字段 | 含义 |
|---|---|
| `headers_s` | 收到响应头。现场实现里，头在预填之前发出，所以它更接近排队，不是预填，也不是 TTFT |
| `ttft_s` | 第一个非空 `delta.content`（或补全里的 `text`）所在 SSE 事件结束的时刻。reasoning 不算。分辨率是完成该事件的那个 socket 块 |
| `first_reasoning_s` | 第一个 reasoning delta。矩阵要求 thinking 关闭。这个字段非空就是模板漂移，不要把该行当成对话档 TTFT |
| `decode_s` | `total_s - ttft_s`。含结尾 usage 帧和 `[DONE]`，比纯解码略长 |
| `total_s` | 看到 `[DONE]` 或连接结束。没有 `[DONE]` 且 HTTP 200 时 `error` 非空 |
| `chunk_times` | 每次 `read(256)` 的序号、相对时间和字节数 |
| `events[].chunk_index` | 完成该 SSE 事件的 socket 块序号 |

SSE 按事件切，不把相邻 `data:` JSON 拼成一个对象。同一事件里的多行 `data:` 先按规范用换行接起来，再 `json.loads` 一次；接出来的文本若不是一个 JSON 对象，记 `malformed`，不影响下一事件。能处理 UTF-8 被切在块中间、`data: [DONE]`、`: keepalive N/M`、`event: ping`、以及没有结尾空行就 EOF。keepalive 记在 `keepalive`，不写入 `prefill`。

`completion_tokens`：有 `usage.completion_tokens` 时用它，`completion_tokens_source=usage`。否则用非空 content 与 reasoning delta 的条数，`source=approx_delta_events`。近似值不是 tokenizer 计数，一条事件也不保证等于一个 token。`decode_tok_s` 只在 `source=usage` 且 `decode_s>0` 时有值，等于 `completion_tokens / decode_s`。

`prompt_tokens` 只来自 `usage.prompt_tokens`。没有 usage 就是 null，不估算。`cached_tokens` 来自 `usage.prompt_tokens_details.cached_tokens`。

`prefill`：只有服务端 payload 出现 `prefill_s`、`prefill_ms`、`prefill_duration_s` 或 prefill tok/s 字段时，该行才是 `status=reported`。mlx-lm 0.31.3 的 usage 只有 `prompt_tokens`、`completion_tokens`、`total_tokens` 和 `cached_tokens`。因此每行都是 `client-unavailable`，汇总里的 `prefill` 就是字符串 `client-unavailable`。

下面这些公式禁止写成预填或解码：

- `completion_tokens / total_s` 当作解码 tok/s
- `prompt_tokens / ttft_s` 当作预填 tok/s
- `ttft_s - headers_s` 当作服务端预填
- keepalive 的 `processed/total` 时间差当作预填秒数。那是未缓存尾部的进度，不是整段 prompt，也不是耗时字段
- `ps` RSS 当作权重大小。Metal 占用不在 RSS 里。`BENCHMARK.md` 已经写过

`headers_s`、`ttft_s`、`keepalive` 可以留给以后看，但本协议的正式预填结论只能是「服务端没报」。

汇总函数 `summarize`：

- `n`、`median`、`p95` 针对有数值的 `ttft_s`。`n_runs` 才是行数，`n_errors` 是带 `error` 的行。失败行不进入分位。
- 中位数用 `statistics.median`（偶数个取中间两点的平均）。
- p95 是 nearest-rank：`rank = ceil(0.95 * n)`，1-based，再夹到 `[1, n]`。`p95_method=nearest_rank_ceil`。
- `n<20` 时 `p95_stable=false`。本矩阵 n 是 1 或 3 或 4，p95 可以落盘，结论写中位数和原始三行，不要把 p95 当稳定分位。
- `identical` 或 `partial` 若同时有 `run_index=0` 和更后的行，汇总带 `pool_warning`。引用热前缀必须用 `by_run_index`，不要用 pooled median。`run_index=0` 是这条正文的第一次，`run_index>=1` 才是热前缀。
- `decode_s_usage_only` 与 `decode_tok_s_usage_only` 丢掉近似 token。`cached_tokens` 另有自己的中位数。

## 6. 内存

`--sample-memory` 在全部请求之前和之后各跑一次，不用 sudo：

- `/usr/bin/memory_pressure`
- `/usr/bin/vm_stat`

每行 JSONL 带 `memory_before`（含原文和 `compact`）。`memory_after` 只在 stdout 汇总里，因为行是跑完就落盘的。`compact` 取 free percentage、page size、free / wired / compressor / swapins / swapouts。页大小以命令输出为准，这台机器本波看到的是 16384。

本波两次只读采样（模型进程已经在，不是压测）：free percentage 一次约 37%，稍后约 21%。差值大，不能用这篇文档里的瞬时值放行后续格子。每一格开始前重新采样。

停止加长或加并发，满足任一即可：

- 上一格有 `error`、没有 `[DONE]`、或 mlx PID 没了
- 准备开下一格时 `free_pct < 20`
- 上一格期间 `Swapins` 增加 ≥ 10000 页（约 160MB 量级的换入，按 16384 字节/页）
- 操作者看到 jetsam、服务无响应，或机器明显开始换页

`Swapins` 是开机以来的累计值，只看格子前后的差。不要用 RSS。wired 和 compressor 一起看，free percentage 单独不够，但低于上面的门槛就停。

## 7. 编排者要跑的矩阵

全部格在放行之后、UI 空闲时跑。`--model default_model`，`--base-url http://127.0.0.1:8081`，`--sample-memory`，`--concurrency 1`，除非写明并发 2。输出文件一格一个，放在 `raw/A4/`。

### 7.1 校准（不是进程冷）

本地 tokenizer 计数完成之后：

`--prompt-tokens 32 --prefix-mode identical --runs 1 --max-tokens 8`

把 `usage.prompt_tokens` 和本地模板计数对上。这一发会让 Metal 和缓存热起来，不能标成进程冷。

### 7.2 每个长度

长度 L：`1000, 4000, 8000, 16000, 20000, 32000`。这里的数字是 `--prompt-tokens`，不是已确认的 token 数。确认值是该格的 `usage.prompt_tokens`。从小到大。进入更长的 L 之前先过第 6 节的门。

必须重启后立刻打的进程冷，只有 L=1000 和 L=8000：

1. 编排者重启 mlx。本脚本没有重启开关，本波代理也不重启。
2. `GET /health` 得到 `{"status":"ok"}`。不要用生成请求当健康检查。
3. `GET /v1/models`，确认 id 仍是本地 9B 目录，不是 Hub id。再 `ps` 确认第 2 节的 flags。thinking 仍是关的。
4. 中间不打别的请求：`--prefix-mode cold --prompt-tokens L --runs 1 --max-tokens 32 --concurrency 1`

1000 与 8000 的重启会重新加载权重，本身就是一次内存尖峰。`free_pct < 25` 时不要为了「补一格进程冷」去重启。4k / 16k / 20k / 32k 不重启；这些长度的前缀冷用下面 `identical` 的 `run_index=0`。长度标头已经错开，`cached_tokens` 应该接近 0。若接近整段 `prompt_tokens`，这格作废，先查是不是标头没生效或中间夹了相同正文。

每个 L，重启格（若有）之后，不重启，按这个顺序：

1. `--prefix-mode identical --runs 3 --max-tokens 32`
2. `--prefix-mode partial --runs 3 --max-tokens 32`
3. `--prefix-mode fresh --runs 3 --max-tokens 32`

读法：

- `identical` 的 `run_index=0`：这条正文第一次。1000 和 8000 若刚做过进程冷，这一发是进程已热、前缀仍冷。
- `identical` 的 `run_index>=1`：热前缀。`cached_tokens` 应接近 `prompt_tokens`，允许模板尾差几个 token，不要要求相等。TTFT 应低于同格的 `run_index=0`。用 `by_run_index`，不要用这三行的 pooled median。
- `partial`：`cached_tokens` 明显大于 0，且明显小于 `prompt_tokens`。
- `fresh`：`cached_tokens` 为 0，或只有极短模板命中。大比例命中则作废。

32k 失败或触发内存门：记下错误，停止更长的长度，不要自动重试。

### 7.3 20000 个汉字

这不是 20000 token。放在 8000 token 那一档成功、且内存门通过之后。若 8000 已经贴着门槛，就挪到整个 token 阶梯后面。失败则停止，不要接着加并发。

不要为汉字档重启，也不要用 `--prefix-mode cold`，免得和进程冷启动混名。不重启，`max_tokens 32`，顺序固定为：

1. `--chars 20000 --prefix-mode fresh --runs 1`（前缀冷，进程保持热）
2. `--chars 20000 --prefix-mode identical --runs 3`
3. `--chars 20000 --prefix-mode partial --runs 3`
4. `--chars 20000 --prefix-mode fresh --runs 3`

`cjk_chars` 必须是 20000。`usage.prompt_tokens` 另记，禁止从字数换算。读法和 7.2 相同：热前缀只看 identical 的 `run_index>=1`。

### 7.4 解码小格

只在 L=1000 的 `identical` 三连成功之后，不重启、不夹 fresh：

`--prompt-tokens 1000 --prefix-mode identical --runs 3 --max-tokens 128 --concurrency 1`

正文和前三连相同，三次都是热前缀。这里可以用三行的 `decode_tok_s`，但只引用 `completion_tokens_source=usage`。不要在 8k 或更长的格子上做这个小格。

### 7.5 并发 2

同时满足才开：

- 并发 1 的 4000 已经成功
- 开跑时 `free_pct >= 25`
- 上一格 `Swapins` 增量 < 10000 页
- 服务端仍然是 `prompt-concurrency 1` 和 `decode-concurrency 1`

只跑两档：4000，以及并发 1 已成功的最大 L。若最大就是 4000，就只跑 4000。每档只跑：

- `identical --runs 4 --concurrency 2 --max-tokens 32`
- `fresh --runs 4 --concurrency 2 --max-tokens 32`

不跑 `cold`，不跑 `partial`。汉字档的并发 2 默认不做；只有 16000 以上的并发 1 已成功且当时 `free_pct >= 30` 才可以加一格 `identical` 与一格 `fresh`，`runs=4`。

任一请求失败，或采样里 `free_pct < 15`，立刻停。后发请求的 `headers_s` 变长只说明在排队。不要把并发 2 的 TTFT 下降写成「并行预填变快」。

## 8. 本波自检

做了：`py_compile`；不联网断言汉字正好 20000 且全是汉字；不同英文长度的公共前缀停在标头换行之前；SSE 能切开 UTF-8、keepalive、`[DONE]`、以及故意接在一起的两段 JSON（记 malformed，不合并）；未设置环境变量时退出码 2。门禁试验的 `--base-url` 是 `http://127.0.0.1:9`，没有连接 8081。

没做：任何生成、任何 tokenize 下载、任何对 8081 的 GET/POST、设置 `KILN_ALLOW_BENCH`、重启 LaunchAgent、修改 benchmarks 或服务 flags。
