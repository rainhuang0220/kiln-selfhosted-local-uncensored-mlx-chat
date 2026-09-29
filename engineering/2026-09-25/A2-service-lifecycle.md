# A2 服务生命周期（只读）

观察窗口：2026-09-25 02:42–02:44 CST。没有 launchctl kickstart/bootout/kill，没有重启，没有改脚本，没有删文件，没有向 MLX 发聊天或生成请求。只做了 `GET /health`。受控恢复测试 **not_done**。

生产配置是 LaunchAgent 正在 exec 的那份脚本，不是仓库 `scripts/start-mlx.sh`。

## 1. 生产 start-mlx 与仓库脚本不是同一份

### finding

`gui/501/com.kiln.mlx` 跑的是 `~/Library/Application Support/kiln/start-mlx.sh`。仓库 `scripts/start-mlx.sh` 不是现场进程。两边 plist 内容相同，都指向生产脚本。唯一会改变采样的标志是温度：生产 `--temp 1.0`，仓库 `--temp 0.6`。thinking、prompt cache、并发没有差异。模型路径在今天的默认值上相同，但解析方式不同。

### evidence

02:42:13 CST，`launchctl print gui/501/com.kiln.mlx`：`state=running`，`runs=6`，`pid=1581`，program `/bin/bash`，参数为 Application Support 的 `start-mlx.sh`，cwd `/Users/rainhuang/Desktop/models/kiln`，stdout `/tmp/kiln-mlx.log`，stderr `/tmp/kiln-mlx.err`。plist 路径 `/Users/rainhuang/Library/LaunchAgents/com.kiln.mlx.plist`。与仓库 `scripts/com.kiln.mlx.plist` 字节相同（sha256 前 12 位 `ea0158d5a1fd`）。`KeepAlive` 真，`ThrottleInterval` 15，`RunAtLoad` 真。

PID 1581 父进程是 `/sbin/launchd`，启动于 2026-09-11 19:50:33 CST，cwd 是 kiln 仓库。命令行与生产脚本一致，不是仓库脚本：

- 解释器：生产脚本写 `kiln/.venv/bin/python`。该路径是符号链接，解析到 Homebrew Python 3.12。进程映像是同一 Cellar 里的 `Python.app`。不是另一套解释器。
- `--model /Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4`
- `--temp 1.0 --top-p 0.95 --top-k 20`
- `--max-tokens 32768 --prefill-step-size 1024`
- `--decode-concurrency 1 --prompt-concurrency 1`
- `--prompt-cache-size 4 --prompt-cache-bytes 4G`
- `--chat-template-args {"enable_thinking":false,"reasoning_effort":"medium"}`
- `--host 127.0.0.1 --port 8081`

`diff`（仓库 → 生产，生产文件 mtime 2026-09-11 14:53）：

| 项 | 生产（现场） | 仓库 `scripts/start-mlx.sh` |
| --- | --- | --- |
| 温度 | `1.0` | `0.6` |
| thinking | `enable_thinking=false`，`reasoning_effort=medium` | 相同 |
| cache | size 4，bytes 4G | 相同 |
| 并发 | decode 1，prompt 1 | 相同 |
| 模型 | 写死上述 9B 绝对路径 | `data/active-model.env` 的 `MODEL_PATH`，否则 `$ROOT/../qwen3.5-9b-hauhau-aggressive-mxfp4` |
| 其他 | 不 source env，无 Python 版本检查 | 会 source；限制 3.11/3.12/3.13 |

`data/active-model.env` 不存在。因此若今天误跑仓库脚本，默认路径会和现在相同，温度仍会从 1.0 变成 0.6。sha256 前 12 位：生产 `70905cadfceb`，仓库 `5ca624780f91`。

`scripts/install-mlx-launchd.sh` 会把生产脚本改写成 `exec` 仓库脚本，然后 bootout/bootstrap/kickstart。那不是当前磁盘上的生产脚本。本次没有跑它。

### proposed change

不要用仓库脚本覆盖 Application Support 脚本，也不要为了「对齐」去跑 `install-mlx-launchd.sh`。若以后要改温度，单独改生产脚本里的 `--temp`，并把改前的 546 字节留下。本次不改。

### risk

把仓库脚本当成生产会在下次重启时把温度打到 0.6，并开始跟随 `active-model.env`。安装脚本还会 bootout 正在服务的 8081。`KeepAlive` 盖不住 bootout：job 被卸掉之后不会自己回来。

### tests

已核对：`launchctl print`、两份脚本 `diff`、PID 1581 命令行、`active-model.env` 不存在。未做：用仓库脚本启动、温度 A/B、重启后 flag 复核。

### rollback

未改文件，没有要回滚的运行中变更。以后若生产脚本被换掉：把 Application Support `start-mlx.sh` 恢复为本次这 546 字节（温度 1.0、写死 9B 路径），plist 保持现内容，再做一次受控拉起。该拉起 **not_done**。

### status

verified_now。脚本替换与受控重启 not_done。

## 2. 8787 是 Kiln BFF；8000 不是

### finding

`127.0.0.1:8787` 是 LaunchAgent `com.kiln.api`，Kiln 的 BFF（`uvicorn app.main:app`）。`127.0.0.1:8000` 是另一个项目 `docxeditor`，不是 Kiln，也不是用户 LaunchAgent。

### evidence

02:42 CST：

| 端口 | PID | 身份 | 父进程 | cwd | 启动 | 启动方式 |
| --- | --- | --- | --- | --- | --- | --- |
| 8787 | 15068 | `python -m uvicorn app.main:app --host 127.0.0.1 --port 8787 --proxy-headers --forwarded-allow-ips=127.0.0.1` | 1 `/sbin/launchd` | `kiln/backend` | 2026-09-15 13:08:31 CST（约 9 天 13 小时） | `gui/501/com.kiln.api`，`state=running`，`runs=34`，脚本 `~/Library/Application Support/kiln/start-api.sh`。无 `--reload` |
| 8000 | 95938 | Homebrew Python 3.14 `-m uvicorn backend.main:app --host 127.0.0.1 --port 8000` | 1 `/sbin/launchd` | `/Users/rainhuang/Desktop/docxeditor` | 2026-09-12 21:53:21 CST（约 12 天） | **不在** `launchctl list`。用户 LaunchAgents、`/Library/LaunchAgents`、`/Library/LaunchDaemons` 的 plist 都没有 `8000` 或 `docxeditor`。ppid 1 只说明父进程已退出后被 launchd 收养，不是 Kiln agent |

`GET http://127.0.0.1:8787/health` → HTTP 200。`status=ok`，`provider.reachable=true`，`http_alive=true`，`base_url` 为空（私有模式），`chat.state=running`，`inference.ready=true`，`consecutive_timeouts=0`，`enable_thinking=false`，模型名 `qwen3.5-9b-hauhau-aggressive-mxfp4`。

`GET http://127.0.0.1:8000/health` 与 `GET /` 都是 HTTP 404。

`KILN_EXPOSURE=private` 在 api.env 和 PID 15068 的环境里都有。api.env 没有 `PAUSE_CHAT_FOR_VIDEO` / `PAUSE_CHAT_FOR_IMAGE`。没有复制其他键。

生产 `start-api.sh` 与仓库 `scripts/start-api.sh` 不同：生产不设置 `KILN_EXPOSURE` 默认值 `local`，路径写死；两边都 source api.env，都没有 `--reload`。现场进程用的是生产脚本。仓库这份不是 8787 的启动方式。

同机 7777：`com.kiln.web` PID 97755（`npm run dev`，2026-09-10 19:19:59）的子进程 97771 是 vite，听 `127.0.0.1:7777`。不是 BFF。Clash 另听 `198.18.0.1:7777`，与 Kiln 无关。

`main.py`、`media.py`、`config.py` 的 mtime 是 2026-09-15 13:45，晚于进程启动。`git diff HEAD` 对这些文件为空，HEAD 提交 `66ff5a7` 时间是 13:08:18，比进程早 13 秒。mtime 是后来碰过文件，内容没有偏离 HEAD。进程无 `--reload`，不能从 mtime 证明内存字节，但磁盘与它启动时所在的这次提交一致。`media_runtime.py` 与 `chat_lifecycle.py` 的 mtime 是 2026-09-14，早于该进程。

### proposed change

不要把 8000 当成 Kiln，也不要重启它来「修窑火」。8787 保持现有 LaunchAgent。本次不重启。

### risk

重启 8787 会丢掉约 9 天的进程内状态（`chat.state`、连续超时计数）。停 8000 会影响 docxeditor，与 Kiln 生命周期无关。

### tests

已做：`launchctl print`、`lsof` 监听、`ps` 的 ppid/lstart/cwd、`GET /health`。未做：登录后的 `/chat`、生成、重启后再看 health。

### rollback

未改 8787/8000。不需要回滚。

### status

verified_now。

## 3. 视频任务会 bootout MLX；图像只有 flux1-dev 会

### finding

磁盘上的视频任务路径会 `launchctl bootout gui/{uid}/com.kiln.mlx`。flux1-dev 也会。其他图像默认不会。恢复不是 `KeepAlive`，而是任务结束时的 `restore_mlx`（再 bootout、bootstrap、kickstart）。本次没有执行这条路径。当前没有在跑的媒体任务，lifecycle 是 `running`。

### evidence

触发链（磁盘源码）：

1. `MediaService._should_park`（`backend/app/services/media.py`）：`kind==video` 时看 `pause_chat_for_video`；`backend==flux1-dev` 时恒为真；其他图像看 `pause_chat_for_image`。
2. 默认值（`backend/app/config.py`）：视频 `True`，图像 `False`。api.env 不覆盖。PID 15068 环境里也没有这两个变量。
3. `_run_job` 在生成前把任务打成 `parking_chat`，再 `lifecycle.park(reason=job_id)`。
4. `ChatLifecycle.park` 未注入回调时调用 `pause_mlx`（`chat_lifecycle.py`）。
5. `pause_mlx`（`media_runtime.py`）：`launchctl bootout` 该 label，然后最多等 30 秒直到 `127.0.0.1:8081` TCP 连不上。不请求 `/health`。

状态名是这些，不是 `VIDEO_SUSPENDED`：

- lifecycle：`running` → `parking` → `parked`；恢复时 `restoring` → `running`。失败为 `recovery_failed`。`park` 自己失败时会再试一次 `restore`，仍失败才留在 `recovery_failed`。
- 任务：`queued`、`enhancing_prompt`、`parking_chat`、`loading`、`generating`、`decoding`、`exporting`、`restoring_chat`，以及终态 `done` / `failed` / `cancelled` / `interrupted`。

恢复条件：

- 正常、取消、生成失败都走 `finally`：只要已经 park 过就 `lifecycle.restore()`。
- `restore_mlx`：先再 bootout 一次，plist 在则 `bootstrap`，然后 `kickstart -k`。最多 180 秒。`_health_ok` 只认 `GET /health` HTTP 200。接着一 token 的 `_smoke_chat`。smoke 失败仍会再看一次 health，200 就返回。超时则抛错，lifecycle 变成 `recovery_failed`。
- API 进程启动时，若 `pause_chat_for_video` 且当时 `/health` 不是 200，lifespan 会调用 `restore_mlx`。当前 8787 自 9 月 15 日起没重启，这条只在下次 API 启动时发生。
- plist 的 `KeepAlive` 只在 job 仍加载、进程自己退出时拉起。`bootout` 卸掉 job，不会靠 KeepAlive 回来。

`chat.db` 只读计数：图像 done 22、失败 1；视频 done 5、失败 2。没有非终态行。最近一条结束于 2026-09-11 01:03:57（flux1-dev），早于当前 MLX PID。`GET /health` 的 `chat.state` 是 `running`。没有 `wan_bench` / `run_prefill` / `activate-model` 进程。

旁路（不是这次的请求路径，本次也没跑）：`scripts/wan_bench.py`、`benchmarks/dialogue_reliability/run_prefill_*.py`、`run_prompt_cache_ab.sh`、`scripts/install-mlx-launchd.sh`、`scripts/activate-model.sh` 也会动这个 LaunchAgent。

### proposed change

不改 park 逻辑。文档和 UI 不要把 bootout 说成「LaunchAgent 崩溃后一两分钟自己起来」。那是两条不同的恢复。本次不改文案。

### risk

真的跑视频或 flux1-dev 会把 8081 卸掉，聊天在恢复完成前不可用。`restore_mlx` 再次 bootout；失败会停在 `recovery_failed`，KeepAlive 不会补救。smoke 失败但 health 200 仍会当成恢复成功。

### tests

已做：读源码、核对默认值和现场 env、只读任务表、确认没有 bench 进程。未做：排队一个视频/flux 任务、观察 bootout、再观察 restore。该项 **not_done**。

### rollback

未触发 park，没有要恢复的 MLX。若以后演练失败：用现有 plist `bootstrap` + `kickstart`，以 `GET /health` 200 且进程命令行仍是第 1 节的生产 flag 为回滚完成条件。演练本身 not_done。

### status

代码路径 verified_now。现场没有处于 park。受控恢复 **not_done**。

## 4. 9 月 11 日的 IndexError 不是 9 月 24–25 日的故障

### finding

stderr 里有 7 次 `IndexError: list index out of range`，全部在 2026-09-11，最后一次 19:50:01，紧挨在当前 PID 启动之前。当前进程启动之后，包括 9 月 24–25 日，IndexError 次数是 0。stdout 日志文件已经不在目录里，不能把一份不存在的尾巴写成今天的故障。

### evidence

`/tmp/kiln-mlx.err` 存在：15,495,913 字节，birth 2026-08-24 03:14:50，扫描时 58,520 行。它从 8 月 24 日一直追加，含当前 PID 之前的多次启动。

当前进程附近（stderr）：

- 43876 行，2026-09-11 19:50:01：`insert_segments` → `IndexError: list index out of range`（`Thread-1 (_generate)`，`mlx_lm/server.py` 的 `_generate`）。
- 43877 行，19:50:33：`GET /health` 200。这与 PID 1581 的 lstart 同一秒，紧挨在下一行新进程 `Starting httpd` 之前。不能把这个 200 当成「生成线程还活着」。
- 43881 行，19:50:34：`Starting httpd at 127.0.0.1 on port 8081...`。此后 `IndexError` 与 `insert_segments` 都是 0。

7 次 IndexError 的时间都在 9 月 11 日：14:55、15:05、19:40、19:43、19:48、19:49、19:50。9 月 12 日另有 79 次 `BrokenPipeError`，不是 IndexError。9 月 24 日访问日志 793 行，9 月 25 日 255 行，其中没有 IndexError。

stderr 尾部（最后 80 行量级，02:44 之前）：大多是 2026-09-25 02:20:26 来自 `127.0.0.1` 的非 HTTP 请求，`code 400, message Bad request version`（该时间点上这类 400 行有 41 条）。随后是 `GET /health` 200：02:39:06 两行，02:43:27 两行。02:43 是本次审计的 GET。这些都不是 IndexError。请求体未写入本文。

stdout：plist 与 fd 1 的名字是 `/private/tmp/kiln-mlx.log`，但目录项不存在（`ls` 找不到）。更早一次 `lsof` 显示该 fd 的 SIZE/OFF 为 0。没有可读的 stdout 尾巴。没有重建这个文件。

`mlx_lm/server.py` 的 `handle_health_check` 不看模型、不看生成线程，固定 HTTP 200 和 `{"status":"ok"}`。本次 `GET http://127.0.0.1:8081/health` 就是这个 body。

### proposed change

不把 9 月 11 日的 traceback 记成今天的宕机。不要为了「清日志」删除 stderr。stdout 路径要等下次由 launchd 自己打开；现在去碰 fd 或重启不在本次范围。

### risk

删掉或截断 stderr 会丢掉唯一还能把 9 月 11 日和今天分开的记录。重启 MLX 才能让 stdout 文件重新出现，但那会中断正在使用的 8081。

### tests

已做：全文件计数、当前进程起点之后的 IndexError 计数、尾部定性。未做：复现 insert_segments、生成冒烟。生成冒烟 **not_done**（禁止向 MLX 发聊天）。

### rollback

未改日志，未重启。无运行中变更可回滚。

### status

verified_now。9 月 24–25 日新 IndexError：没有。

## 5. 公网隧道进程在跑；历史退出码不是这一次的失败

### finding

`com.kiln.web-tunnel` 当前在跑。转发目标是本机 `127.0.0.1:8787`，远端监听名是 `127.0.0.1:17777`。本机 17777 没有人听，这符合反向转发。另一条 `com.kiln.mtplx-tunnel` 也在跑，转发的是 8081，不是这条公网页路径。没有读取私钥。

### evidence

02:42 CST：

- `gui/501/com.kiln.web-tunnel`：`state=running`，`pid=30344`，`runs=1127`，`last exit code=1`。脚本是 `~/Library/Application Support/kiln/run-web-tunnel.sh`，与仓库 `scripts/run-web-tunnel.sh` 字节相同（sha256 前 12 位 `91f20885ba9b`）。进程启动 2026-09-25 02:36:34 CST，父进程 launchd，cwd `/`。
- 子进程 ssh：`-R 127.0.0.1:17777:127.0.0.1:8787`，对端 `kiln-tunnel@175.24.134.228`。到 `175.24.134.228:22` 为 ESTABLISHED（本机源 `10.38.178.122`）。身份文件参数已省略。
- 本机 `lsof`：`127.0.0.1:17777` 无 LISTEN。
- 脚本逻辑：先等路由和本机目标端口，再 `ssh -R LISTEN:LOCAL`；远端 17777 没打开就退出；之后每 15 秒再查一次，查失败写 `STATE=REMOTE_LISTENER_LOST` 并退出。
- stdout 日志 mtime 2026-09-25 02:36:35，末行是 `forward 127.0.0.1:17777 -> 127.0.0.1:8787 via kiln-tunnel@175.24.134.228`。stderr mtime 02:36:20，早于本 PID。尾部那些 `REMOTE_LISTENER_LOST`、`ROUTE_OK_TCP22_FAIL`、`remote port forwarding failed` 是上一次退出留下的，不是 02:36:34 这次启动之后的新失败。`runs=1127` 与 `last exit code=1` 只说明历史上经常重启。
- 02:42 时 bash 仍在，并有一个 `sleep 15` 子进程，符合复查循环。按脚本，复查失败会退出。没有另开连接去探针 VPS。

`com.kiln.mtplx-tunnel`：`state=running`，`pid=30341`，启动 02:36:23，`runs=22621`，上次退出码 255。命令是 `ssh -N -R 127.0.0.1:8081:127.0.0.1:8081 ubuntu@175.24.134.228`，同样 ESTABLISHED。不是公网页面用的 17777→8787。

`KILN_EXPOSURE=private` 存在（见第 2 节）。没有记录 token 或口令。

### proposed change

不要为了把 `runs` 或 stderr 尾巴「清干净」而重启隧道。本次不改脚本、不轮换密钥。

### risk

重启隧道会打断公网入口。把 stderr 旧行当成现在的故障会误判一条已经重新 forward 成功的隧道。

### tests

已做：`launchctl print`、进程与 ESTABLISHED、脚本哈希、日志 mtime 与末行。未做：从 VPS 或公网再探 17777、TLS 页面检查。独立远端探测 **not_done**。

### rollback

未改隧道。无运行中变更可回滚。

### status

进程与脚本逻辑 verified_now。独立远端监听探测 not_done。

## 6. 今天实际表达的状态，以及哪些只是 HTTP 200

### finding

请求的六个名字里，代码只实现了 `degraded` 这个字符串。现场值不是它。现场是 lifecycle `running`，加上两边 `/health` 的 HTTP 200。`AVAILABLE`、`BUSY`、`VIDEO_SUSPENDED`、`STARTING`、`OFFLINE` 都不是后端状态名。受控恢复没有做。

### evidence

磁盘上的机器：

```
running --park--> parking --bootout 成功--> parked
parking 或 restoring 失败 --> recovery_failed
parked --restore--> restoring --restore_mlx 成功--> running

GET /health status:
  ok       = provider.reachable 且 inference.ready
  degraded = 二者缺一
provider.reachable = http_alive = mlx GET /health 的状态码是 200
inference.ready    = 连续超时次数 < 3
```

02:43 的现场值：`running` + `status=ok` + `reachable=true` + `timeouts=0`。8081 的 body 只有 `{"status":"ok"}`。媒体任务没有在飞的行。

对照：

| 名字 | 代码里有没有 | 今天现场 |
| --- | --- | --- |
| AVAILABLE | 没有这个标识。最近似是 `running` 且 `status=ok` 且 `reachable` | 这三个布尔现在都真。`reachable` 只是 HTTP 200 |
| BUSY | 没有。最近似是聊天里的 `generation already in progress`，以及 mlx `--decode-concurrency 1`。`/health` 不报告它 | 未观测到在飞任务或超时 |
| VIDEO_SUSPENDED | 没有。最近似是 `parking` / `parked` / `restoring`，而且视频默认会 bootout | 现在是 `running`，不是挂起 |
| STARTING | 没有。模型目录另有 `restarting`，那是换模型，不是这次 MLX 启动。restore 等待没有单独的 STARTING | 两个服务都已是 running，不是启动中 |
| DEGRADED | 有，就是 `/health` 的 `"degraded"` | 现在是 `"ok"`。三次超时且 8081 仍 200 时会变成 degraded，但 UI 离线横幅不看这个字段 |
| OFFLINE | 后端没有这个枚举。UI「模型暂时离线」只在 `provider.reachable` 不为真时出现（`web/src/app.tsx`）。侧栏在 `chat.state != running` 时优先「视频生成中」（`SidebarFooter.tsx`） | 本次 health 不会让这句成立。vite 进程自 9 月 10 日起，源码 mtime 更晚；横幅句子以当前源码为准，没有在浏览器里点开核对 |

只是 HTTP 200、不能再外推的部分：

- 8081 `/health` 不检查生成线程。9 月 11 日 19:50 的 IndexError 就发生在该线程，同一秒窗口里仍有一条 `/health` 200。
- 8787 `reachable` / `http_alive` 是同一次 200，不是第二次探测。
- `restore_mlx` 可以在一 token smoke 失败后仍因 200 返回。
- `status=ok` 不表示没有人占用 decode 槽，也不表示没有 park。

### proposed change

在有一次 not_done 的恢复演练之前，不要把这六个英文名写进 API。若以后要加，`VIDEO_SUSPENDED` 应对 `parked` 而不是对 `reachable=false`，`OFFLINE` 不要只等于 HTTP 非 200。本次不改代码。

### risk

用 200 表示可用，会在生成线程已死或正在 bootout 时仍显示在线。用「离线」概括 park，会把故意卸掉的 MLX 说成崩溃。

### tests

已做：两边 `GET /health`、源码对照、任务表。未做：浏览器横幅、park/restore 全流程、生成线程被打死后 `/health` 是否仍为 200 的受控复现。这些都是 **not_done**。

### rollback

未改状态机。无运行中变更可回滚。

### status

现场读数 verified_now。六个名字的产品状态机未实现。受控恢复测试 **not_done**。
