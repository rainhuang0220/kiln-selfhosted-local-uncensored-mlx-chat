# A2 — Kiln LaunchAgent 与本机 MLX 只读取证

审计窗口：2026-09-24 20:53–21:06 CST。主机 `rainhuangdeMacBook-Pro-7.local`，uid `501`。只读：没有 kickstart / kill / bootout / bootstrap，没有改 plist 或脚本，没有删除 `/tmp` 日志，没有 POST 生成请求，没有读取 `api.env`。环境只记录变量名。日志里的非 HTTP 载荷（含 `bea_key` 一类字段）已脱敏，不写入本报告。

原始输出：`/Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/raw/A2/`。

## 结论

本机 `com.kiln.mlx` **在跑，不是重启循环，模型已加载，环回 8081 健康检查是 200**。本审计没有发 chat/completions，所以**不把「生成已死」写成已证实**；按任务口径，受控复测标 **UNTESTED**。旁证见日志节：当前这只进程在 21:01:59 仍有一次 `POST /v1/chat/completions` 200，并且同一秒有 `Prompt processing progress`。那不是本审计发出的请求。

隧道连通性不判断，留给 A11。审计窗口里两条隧道 job 的 PID 换过，mlx / api / web 的 PID 没换。

事先线索核对：`gui/501/com.kiln.mlx` state=running、pid=1581、program=`/bin/bash` + `start-mlx.sh`、cwd=`/Users/rainhuang/Desktop/models/kiln`、stdout/stderr 配置路径、runs=6、监听 `127.0.0.1:8081`，与 `launchctl print` 和 `lsof` 一致。补充：活进程映像已经是 Python（脚本 `exec`），不是 bash；`/tmp/kiln-mlx.log` 的目录项在审计时不存在，进程 fd 1 仍指着一个 0 字节的已打开文件。

## 1. Agent 清单

用户域 `launchctl list` 只有这五个 `com.kiln.*`（21:06:26 快照）。`print-disabled gui/501` 里 mlx / api / web / web-tunnel 都是 enabled；mtplx-tunnel 不在 disabled 列表里，但 print 显示它在跑。

| label | 21:06 PID | 上次退出状态 | state（print） | runs | 程序 | 监听/备注 |
| --- | --- | --- | --- | --- | --- | --- |
| `com.kiln.mlx` | 1581 | -15（SIGTERM） | running | 6 | bash → `~/Library/Application Support/kiln/start-mlx.sh` | `127.0.0.1:8081` |
| `com.kiln.api` | 15068 | -15 | running | 34 | bash → `start-api.sh` | 活进程是 uvicorn `127.0.0.1:8787`，etime 约 9 天 7 小时 |
| `com.kiln.web` | 97755 | 143（128+15） | running | 4 | bash → `start-web.sh` | 子进程 node/vite `127.0.0.1:7777`，etime 约 14 天 |
| `com.kiln.web-tunnel` | 29788 | 1 | running（20:57 print 时 pid 还是 99626） | 1099 | bash → `run-web-tunnel.sh` | 本报告不测隧道 |
| `com.kiln.mtplx-tunnel` | 29156 | 255 | running | 22600 | `/usr/bin/ssh -N -R 127.0.0.1:8081:127.0.0.1:8081 ubuntu@175.24.134.228` | 本报告不测隧道 |

PID 变化（只记观察，不解释原因）：

- 20:53：web-tunnel `99626`，mtplx `99513`。
- 20:57 print：web-tunnel 仍 `99626`（runs=1099，last exit 1）；mtplx 已变成 `26156`（runs=22600，last exit 255）。
- 21:00 与 21:06：web-tunnel `29788`，mtplx `29156`。mlx `1581`、api `15068`、web `97755` 全程未变。

五个 gui job 的 print 都有 `immediate reason = inefficient`，同时 `state = running`。这不是 mlx 独有，不能单独当成故障。

另外：

- `system/com.kiln.vps-direct-route`：LaunchDaemon，print 路径 `/Library/LaunchDaemons/com.kiln.vps-direct-route.plist`，`state = not running`，`runs = 21240`，`last exit code = 0`，`run interval = 20 seconds`，并监视 `/Library/Preferences/SystemConfiguration`。这是周期性短任务退出 0，不是常驻 mlx。没有执行 `ensure-vps-direct-route.sh`。
- `/Library/LaunchAgents/com.kiln.vps-direct-route.plist` 在目录列表里（root:wheel）。本次读不到内容。用户 LaunchAgents 目录下的五个 `com.kiln.*.plist` 都读了。

plist 与 print 一致的要点：mlx/api/web 都是 `RunAtLoad` + `KeepAlive` + `ThrottleInterval` 15 + `ProcessType=Interactive`，工作目录都是 `/Users/rainhuang/Desktop/models/kiln`。mlx 的环境变量只有 `HOME`、`TOKENIZERS_PARALLELISM=false`、`PATH=/opt/homebrew/bin:/usr/bin:/bin`。

## 2. 活进程 `com.kiln.mlx`（pid 1581）

`ps`（20:57:28，21:06 复核 pid/etime 仍是同一只）：

- pid `1581`，ppid `1`（launchd），uid 501，stat `S`
- etime `13-01:15:53`（21:06），`lstart` = 2026-09-11 19:50:33 CST
- 无子进程
- 命令行：

```text
/opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -m mlx_lm.server \
  --model /Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4 \
  --host 127.0.0.1 --port 8081 \
  --max-tokens 32768 --temp 1.0 --top-p 0.95 --top-k 20 \
  --decode-concurrency 1 --prompt-concurrency 1 \
  --prefill-step-size 1024 \
  --prompt-cache-size 4 --prompt-cache-bytes 4G \
  --chat-template-args {"enable_thinking":false,"reasoning_effort":"medium"}
```

`lsof -a -p 1581 -d cwd`：`/Users/rainhuang/Desktop/models/kiln`。

环境变量**名**（14 个，无 key/token/secret 这类名字）：`SHELL, TMPDIR, USER, SSH_AUTH_SOCK, PATH, XPC_FLAGS, XPC_SERVICE_NAME, SHLVL, HOME, TOKENIZERS_PARALLELISM, LOGNAME, OSLogRateLimit, __CF_USER_TEXT_ENCODING, __PYVENV_LAUNCHER__`。`__PYVENV_LAUNCHER__` 说明是 venv 的 python 再 exec 到 Homebrew 3.12.12，与脚本里的 `.venv/bin/python` 相符。

内存不要看 RSS。20:58 `ps` RSS = 6704 KB，VSZ = 440573264 KB。`footprint -p 1581`：

- phys_footprint **5086 MB**，峰值 **7944 MB**
- 其中 IOAccelerator（graphics）dirty **4872 MB**

磁盘模型目录在，`du -sh` = **5.3G**。分片 `model-00001-of-00002.safetensors` 4.8G、`model-00002-of-00002.safetensors` 515M。`lsof -p 1581` 共 76 行，**没有打开任何 `.safetensors`**。权重不在文件描述符上，而在 GPU/IOAccelerator 占用里。这和「模型没加载」相反。

## 3. 监听

`lsof -nP -iTCP:<port> -sTCP:LISTEN`（20:58）：

| 端口 | 结果 |
| --- | --- |
| 8081 | 只有 `Python 1581`，`127.0.0.1:8081`。不是 `0.0.0.0` |
| 8787 | `Python 15068`，`127.0.0.1:8787`。命令行是 `uvicorn app.main:app --host 127.0.0.1 --port 8787 --proxy-headers --forwarded-allow-ips=127.0.0.1`，对得上 `com.kiln.api` |
| 7777 | 两个不同地址：`node 97771`（ppid 97755）`127.0.0.1:7777`，命令为 kiln `web/node_modules/.bin/vite --host 127.0.0.1 --port 7777 --strictPort`；另有 `ClashX 59877` 听 `198.18.0.1:7777`。Kiln web 是环回那只 |
| 17777 | 该次快照没有 LISTEN。只作本地观察，隧道结论留给 A11 |

pid 1581 另有一条已 `CLOSED` 的出站套接字 `198.18.0.1:53037 -> 198.18.3.59:443`，不是监听。

## 4. GET（本审计发出，无 POST）

21:04:52 与 21:06 两次 GET，结果相同。服务端 `BaseHTTP/0.6 Python/3.12.12`。响应带 `Access-Control-Allow-Origin: *`。

| URL | 状态 | body |
| --- | --- | --- |
| `http://127.0.0.1:8081/v1/models` | **200** | `{"object":"list","data":[{"id":"/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4","object":"model","created":1790255186}]}` |
| `http://127.0.0.1:8081/health` | **200** | `{"status":"ok"}` |
| `http://127.0.0.1:8081/` | **404** | `Not Found` |

`/` 的 404 与历史日志一致（此前仅 2 次 `GET /` 404）。健康路径是 `/health`，不是 `/`。model id 就是命令行上的本地目录，不是 Hub repo id。

## 5. 日志

- 配置：stdout `/tmp/kiln-mlx.log`，stderr `/tmp/kiln-mlx.err`。`/tmp` 与 `/private/tmp` 同一文件。
- 21:01 前后：`/private/tmp/kiln-mlx.log` **目录项不存在**。`lsof` fd 1 仍是该路径，SIZE/OFF = 0，inode 43455979，`find -inum` 找不到。等于进程握着一个空的、已不在目录里的 stdout。没有可 tail 的 stdout 内容。
- stderr 在：`/private/tmp/kiln-mlx.err`，约 15.3 MB，57897 行，属主 rainhuang:wheel。末尾仍在长（审计期间有新的 GET/POST 行）。

可解析的 HTTP 访问行 12577 条。状态分布：

| 请求 | 次数 | 首次 | 最近 |
| --- | --- | --- | --- |
| `GET /health` → 200 | 11006 | 24/Aug/2026 03:15:31 | 24/Sep/2026 21:01:21 |
| `POST /v1/chat/completions` → 200 | 1492 | 03/Sep/2026 20:03:34 | **24/Sep/2026 21:01:59** |
| `POST /v1/completions` → 200 | 43 | 03/Sep/2026 21:14:49 | 11/Sep/2026 19:50:01 |
| `POST /v1/chat/completions` → 404 | 22 | 03/Sep/2026 21:13:49 | 11/Sep/2026 19:50:37 |
| `GET /v1/models` → 200 | 10 | 03/Sep/2026 17:56:49 | 24/Sep/2026 20:53:17 |
| `GET /` → 404 | 2 | 10/Sep/2026 | 10/Sep/2026 |

`Prompt processing progress` 共 4645 行，最后一条时间戳 **2026-09-24 21:01:59**，与上面最后一次 POST 200 同一秒。没有把提示词正文抄进报告；这些行是进度计数，不是 prompt 文本。

另外约 28856 行含 `wup_version` 或 `Bad request version`。来自 `127.0.0.1` 的非 HTTP 二进制请求，服务器回 **400**。特征字段名是 `wup_version`、`TYPE_COMPRESS`、`encr_type`。载荷里有看起来像密钥的字段，**已脱敏，不记录值**。这没有把进程打退出去：400 之后仍有 `/v1/models` 200 和 `/health` 200。文件末尾（脱敏后）最后三行正常访问是：

```text
24/Sep/2026 20:53:17 GET /v1/models 200
24/Sep/2026 20:59:52 GET /health 200
24/Sep/2026 20:59:52 GET /health 200
```

启动记录：`Starting httpd at 127.0.0.1 on port 8081` **45 次**，从 2026-08-24 03:15:31 到 **2026-09-11 19:50:34**。最后一次与 pid 1581 的 lstart（19:50:33）对齐。此后没有新的 Starting 行。每次 Starting 都配有一条：

```text
shell-init: error retrieving current directory: getcwd: cannot access parent directories: Operation not permitted
```

共 45 条，包括当前这次启动。审计时 `lsof` cwd 已经是仓库目录，所以这条历史警告**不等于当前工作目录丢失**。原因未再查（没有改环境）。

`runs = 6` 小于日志里的 45 次，因为 stderr 跨 job 重载追加，计数器会重置。当前这次加载的最后 6 次 Starting 是 09-11 19:43:36、19:47:44、19:48:17、19:49:03、19:49:49、19:50:34。间隔从几十秒到数分钟，长于 `ThrottleInterval` 15 秒，不像撞在节流上的崩溃紧循环。上次终止信号是 `Terminated: 15`。19:50:34 之后这只 pid 已连续约 13 天，**当前不是 restart loop**。机器 boot 时间是 2026-05-31 12:37:34，uptime 约 116 天；这只 mlx 不是从开机一直活到现在。

异常（整份 stderr，214 段 Traceback）：

- `BrokenPipeError: [Errno 32] Broken pipe`：206 次。栈在 `mlx_lm/server.py` `handle_completion` 写 SSE（`wfile.write` → `sendall`）时客户端断开。当前进程起点（19:50:34 那条 Starting）之后还有 **79** 次 Traceback，全部是这个 BrokenPipe，进程仍是 `S`。
- `IndexError: list index out of range`：7 次。栈在 `server.py` `_generate` → `generate.py` `insert_segments` 的 `len(seq[-1])`。最近时间都在 **09-11 19:50:01 及更早**，属于最后那次启动之前的短命进程。当前这只进程的日志里 **没有** IndexError。
- `ConnectionResetError: [Errno 54]`：1 次，2026-09-11 19:20:00，也在当前进程之前。
- 没有 `Address already in use`、`Killed`、`out of memory`。

当前进程启动后约 3 秒（19:50:37）有一条 Hugging Face `GET .../qwen3.5-9b-hauhau-aggressive-mxfp4/revision/main` → **401 Unauthorized**。这是该文件里最后一条 HF 请求。服务没有因此退出；`/v1/models` 返回的是本地路径。401 只说明当时 Hub revision 检查未授权，不能解释成「现在模型没加载」。

代表性栈（无 prompt 正文）：

```text
File ".../mlx_lm/server.py", line 1202, in do_POST
    self.handle_completion(request, stop_words)
File ".../mlx_lm/server.py", line 1489, in handle_completion
    self.wfile.write(f"data: {json.dumps(resp)}\n\n".encode())
BrokenPipeError: [Errno 32] Broken pipe
```

```text
File ".../mlx_lm/server.py", line 776, in _generate
    (uid,) = batch_generator.insert_segments(...)
File ".../mlx_lm/generate.py", line 1646, in insert_segments
    if len(seq[-1]) != 1:
IndexError: list index out of range
```

每次历史启动还有一条 `UserWarning: mlx_lm.server is not recommended for production...`（`server.py:1723`）。这是库的警告，不是崩溃。

## 6. 命令行和脚本

三份对照：

| 项 | 活进程 argv | `~/Library/Application Support/kiln/start-mlx.sh`（mtime 2026-09-11 14:53） | 仓库 `scripts/start-mlx.sh`（mtime 2026-09-14 02:42） |
| --- | --- | --- | --- |
| 谁被 launchd 执行 | 已 `exec` 成 python | plist 的 ProgramArguments | **不是** launchd 的入口 |
| model | 绝对路径 `.../qwen3.5-9b-hauhau-aggressive-mxfp4` | 同一绝对路径，写死 | `MODEL_PATH`，否则 `$ROOT/../qwen3.5-9b-hauhau-aggressive-mxfp4`。`data/active-model.env` 与 Application Support 下的 `active-model.env` **都不存在**。launchd 环境没有 `MODEL_PATH`。按仓库脚本从仓库根解析，默认路径与现在相同 |
| host / port | `127.0.0.1:8081` | 同 | 同 |
| prefill-step-size | 1024 | 1024 | 1024 |
| prompt-cache-size / bytes | 4 / 4G | 4 / 4G | 4 / 4G |
| temp | **1.0** | **1.0** | **0.6** |
| 其余采样与并发 | max-tokens 32768，top-p 0.95，top-k 20，decode/prompt concurrency 1，chat-template-args `enable_thinking=false`、`reasoning_effort=medium` | 同 | 同 |
| Python 版本门 | 实际 3.12.12 | 无检查 | 只允许 3.11/3.12/3.13。当前解释器过得了这道门，但活进程没走这段脚本 |

`diff -u` 已安装脚本 vs 仓库脚本：实质差别就是仓库多了 `active-model.env`、解释器检查，以及 `--temp 0.6`。其余 flag 相同。`diff` LaunchAgents plist vs `scripts/com.kiln.mlx.plist` **为空**，两份 plist 相同。

`scripts/install-mlx-launchd.sh` 若执行，会把 Application Support 的 `start-mlx.sh` 写成 `exec "$ROOT/scripts/start-mlx.sh"` 的包装，并写出一份 PATH 含 `/usr/local/bin`、不设 `HOME` 的 plist。磁盘上的脚本**不是**这个包装，而是直接 `exec .venv/bin/python -m mlx_lm.server`。本次没有运行安装脚本。因此：**现在跑的是 Application Support 里 temp 1.0 的那份，不是仓库里 temp 0.6 的那份。** 进程启动于 09-11 19:50，早于仓库脚本 09-14 的 mtime，重启之前不会吃到仓库改动。

已读、未执行的相关脚本：

- 已安装 `start-api.sh`：若存在则 `source` api.env（未读），然后 uvicorn `127.0.0.1:8787`。与活进程 15068 一致。仓库版额外默认 `KILN_EXPOSURE=local`，并检查 `.venv/bin/python`。
- 已安装 `start-web.sh`：把 PATH 固定到 nvm Node v24.18.0，`npm run dev --prefix web -- --host 127.0.0.1 --port 7777 --strictPort`。与 97755/97771 一致。仓库版用 `npm` 并先检查 `web/node_modules`。

## 7. 分类（只按证据）

| 假设 | 判定 | 证据 |
| --- | --- | --- |
| 进程不在 | 否 | 21:06 pid 1581 仍在，state=running |
| 当前 restart loop | 否 | etime 13 天+；最后一次 Starting 是 09-11 19:50:34，之后无新启动。更早有过集中重启（日志 45 次 Starting，当前 job `runs=6`，上次信号 15），那是历史，不是现在 |
| 进程在但模型没加载 | 否 | `/v1/models` 200 且 id 为本地目录；GPU footprint 5086 MB（IOAccelerator 4872 MB）；磁盘分片在。RSS 6.7 MB 不能用来否定加载，MLX 权重不在 RSS 里。safetensors 未保持打开，只能说明加载后关了文件 |
| 健康是好的但生成已死 | **UNTESTED（本审计）** | 本审计只做了 GET。不能把「生成已死」标成证实。反向旁证：当前进程日志里最后一次 `POST /v1/chat/completions` 是 24 Sep 21:01:59 的 **200**，同一秒有 Prompt processing。那次请求不是本审计发的，也没有看响应 body，所以不把「本审计已验证生成」写成结论 |
| 本地 vs 隧道 | 本地监听正常 | `127.0.0.1:8081` 由 pid 1581 持有，`/health` 与 `/v1/models` 200。隧道 PID 在窗口内变化、runs 很高（web-tunnel 1099 / mtplx 22600），**连通性留给 A11** |

## 证据索引

- `raw/A2/01-launchctl-mlx.txt` 及 api/web/web-tunnel/mtplx/vps print
- `raw/A2/01-launchctl-list.txt` PID 快照
- `raw/A2/02-plist-com.kiln.*.plist`
- `raw/A2/03-ps.txt`、`03-env-names.txt`
- `raw/A2/04-lsof-listen.txt`、`05-footprint.txt`、`05-lsof-full.txt`、`05-model-dir.txt`
- `raw/A2/06-http-summary.txt`、`06-err-tail80.txt`（载荷已脱敏）、`06-err-tracebacks.txt`
- `raw/A2/07-body-v1-models.txt`、`07-body-health.txt`、`07-body-root.txt` 及对应 `.hdr`
- `raw/A2/08-diff-start-mlx.txt`；`08-diff-plist.txt` 为 0 字节，表示两份 plist 无差异
