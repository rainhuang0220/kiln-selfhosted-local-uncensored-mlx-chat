# A11：公网页到本机 MLX 的请求链

日期：2026-09-24。观测窗口约 20:57–21:01 +0800。只读。没有重启 ssh、Caddy、Clash 或 LaunchAgent，没有执行 `ensure-vps-direct-route.sh` 或安装脚本，没有读 `kiln-tunnel` 私钥，没有登录，没有发聊天或生成请求。原始记录在 `kiln/engineering/2026-09-24/raw/A11/`。

## 结论

仓库文档里的公网路径是：浏览器 → `kiln.plainlist.space:443` 上的 nginx 静态页 → 仅 API 路径反代到 VPS `127.0.0.1:17777` → SSH 反向隧道 → 本机 `127.0.0.1:8787` FastAPI → 本机 `127.0.0.1:8081` 的 `mlx_lm.server`。

本机此刻能看见这条隧道的 Mac 侧：`ssh` PID 29891 的 `-R 127.0.0.1:17777:127.0.0.1:8787` 已对 `175.24.134.228:22` 建立连接。API（PID 15068）和 MLX（PID 1581）都在环回地址上监听。VPS 上的 nginx/Caddy 进程、`ss` 监听和 TLS 证书没有从这台 Mac 直接看到，标为 **NOT OBSERVED**。唯一一次公网 `curl` 被 Clash 假 IP 截住，没有打到 VPS。

并行还开着第二条隧道：PID 29156，`-R 127.0.0.1:8081:127.0.0.1:8081`。README 的公网页不经过它。它对应 `deploy/compose.yml` 里跑在 VPS 上的 API 去连 MLX。VPS 上有没有那个消费者，**NOT OBSERVED**。

「本地生成正常但 VPS 超时」这一类故障：**UNTESTED**。没有生成请求，公网探测也没有到达 VPS，没有可比的耗时。

## 1. 本机进程（21:01:17 +0800）

| LaunchAgent | PID | 上次退出 | 本次看到的进程 |
| --- | --- | --- | --- |
| `com.kiln.mlx` | 1581 | -15（历史 SIGTERM，不是当前进程退出） | `mlx_lm.server`，已运行约 13 天 1 小时 |
| `com.kiln.api` | 15068 | -15，同上 | `uvicorn app.main:app --host 127.0.0.1 --port 8787 --proxy-headers --forwarded-allow-ips=127.0.0.1`，约 9 天 8 小时 |
| `com.kiln.web` | 97755 | 143 | `npm run dev --host 127.0.0.1 --port 7777 --strictPort`，约 14 天。子进程 node PID 97771 |
| `com.kiln.web-tunnel` | 29788 | 1 | `bash .../run-web-tunnel.sh`，本次只活了约 3 分 32 秒 |
| 其子进程 | 29891 |  | `ssh -R 127.0.0.1:17777:127.0.0.1:8787 kiln-tunnel@175.24.134.228`，约 3 分 31 秒 |
| `com.kiln.mtplx-tunnel` | 29156 | 255 | `/usr/bin/ssh -R 127.0.0.1:8081:127.0.0.1:8081 ubuntu@175.24.134.228`，约 3 分 47 秒 |
| `com.openssh.ssh-agent` | 67675 | 0 | 系统 ssh-agent，不是 Kiln 转发 |

没有 `autossh`。保活靠 launchd `KeepAlive`。

观测窗口内两条隧道都重启过。第一次 `launchctl list` 里 web-tunnel 还是 PID 99626（bash 已跑约 44 分钟）；大约 20:57 它退出，被 29788/29891 换掉。mtplx 当时没有 PID、上次退出 255，随后变成 29156。到 21:01 这两个新 PID 仍在，且对 `175.24.134.228:22` 为 ESTABLISHED，源地址 `192.168.43.78`（en0 网段，不是 utun）。

29891 的命令行（身份文件只记路径，未读内容）：

```
ssh -M -S /tmp/kiln-web-tunnel.sock -N -T \
  -i "$HOME/Library/Application Support/kiln/kiln-tunnel" \
  -o IdentitiesOnly=yes -o ControlMaster=yes -o ControlPersist=no \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=2 \
  -o BatchMode=yes -o ConnectTimeout=15 \
  -R 127.0.0.1:17777:127.0.0.1:8787 \
  kiln-tunnel@175.24.134.228
```

控制套接字 `/tmp/kiln-web-tunnel.sock` 存在，mtime 20:57。私钥文件权限 `600`、399 字节。`~/.ssh/config` 没有 kiln、plainlist 或该 VPS 的 Host。无关的 `Host jhx`（`RemoteForward 7890`，`ServerAliveInterval 60`）不在这条路径上。Kiln 的 SSH 选项全部来自命令行，不来自 ssh config。

包装脚本在转发成功后每 15 秒用另一条 `ssh -o ConnectTimeout=8 ubuntu@175.24.134.228` 去连 VPS 的 `127.0.0.1:17777`（超时 2 秒）。失败会打印 `REMOTE_LISTENER_LOST` 并以 1 退出。29788 连续活过多个 15 秒周期，按脚本逻辑这些检查当时是通过的。这是间接证据。本代理没有登录 VPS 执行 `ss`/`lsof`，所以 VPS 监听套接字仍标 **NOT OBSERVED**。`ExitOnForwardFailure=yes` 且 29156 持续存活，同样只说明 8081 的远程 bind 在握手时被接受，不能代替 VPS 侧的监听检查。

`Application Support/kiln/run-web-tunnel.sh` 与仓库 `scripts/run-web-tunnel.sh` 无差异。`install-web-tunnel.sh` 开头注释仍写「转到本机 7777」，那是过时注释；同一文件的 `LOCAL` 默认值、已安装 plist 和正在跑的 `-R` 都是 `127.0.0.1:8787`。

## 2. 监听

`lsof -nP -iTCP -sTCP:LISTEN`：

| 地址 | PID | 是什么 |
| --- | --- | --- |
| `127.0.0.1:8081` | 1581 Python | MLX。公网路径的模型端口，只绑环回 |
| `127.0.0.1:8787` | 15068 Python | Kiln API。隧道落地端口 |
| `127.0.0.1:7777` | 97771 node | 本地 Vite。`allowedHosts` 只有 `127.0.0.1` 和 `localhost`，不是公网源 |
| `198.18.0.1:7777` | 59877 ClashX | Clash 假 IP 网段上的端口，不是 Kiln |
| `17777` | 无 | 反向监听在 VPS 上，本机没有 |

MLX 命令行与 `Application Support/kiln/start-mlx.sh` 一致：模型 `qwen3.5-9b-hauhau-aggressive-mxfp4`，`--max-tokens 32768`，`--decode-concurrency 1`，`--prompt-concurrency 1`。没有对 `:8081/health` 发请求。

## 3. 配置里的两条边缘，现网是哪条没有看到

**文档和 nginx 仓库文件（维护机路径，README 也是这条）：**

`deploy/nginx-kiln.plainlist.space.conf` 注释写明现网文件应在 `/www/server/panel/vhost/nginx/kiln.plainlist.space.conf`。该远程文件 **NOT OBSERVED**。

- `:80` 除 ACME 外 301 到 `https://kiln.plainlist.space`
- `:443` 静态根 `/www/wwwroot/kiln.plainlist.space`，`try_files` 回 `index.html`
- `GET /` 不进隧道
- `/health`、`/docs`、`/redoc`、`/openapi.json` 直接 `return 404`，不进隧道
- `/auth`、`/chat`、`/conversation`、`/context`、`/memory`、`/models`、`/generate`、`/v1/` 反代到 `http://127.0.0.1:17777`
- `X-Forwarded-For` 设成 `$remote_addr`（覆盖，不追加）。与 API `TRUST_PROXY_HEADERS=true` 的前提一致

**另一套，Caddy + 把 API 放在 VPS 上：**

`deploy/Caddyfile`（镜像 `caddy:2.8-alpine`）把 API 路径反代到 **VPS 自己的** `127.0.0.1:8787`，不是 `17777`。`deploy/compose.yml` 用 host 网络跑 API，并设 `MLX_BASE_URL=http://127.0.0.1:8081`。那要靠 mtplx 那条 `-R 8081`。Caddyfile 用 `header -Server` 去掉 Server 头，所以即使探测成功，空的 Server 也不能单独证明是 Caddy。

正在跑的 Mac 代理同时满足这两套的 Mac 侧：17777→8787 和 8081→8081。公网页按 README 走第一套。VPS 上实际加载的是 nginx 还是 Caddy，**NOT OBSERVED**。

本机 `api.env` 只有这些项（没有令牌类的键）：`KILN_EXPOSURE=private`，`COOKIE_SECURE=true`，`TRUST_PROXY_HEADERS=true`，`AUTH_SIGNUP=false`，`KILN_PUBLIC_ORIGIN=https://kiln.plainlist.space`。没有覆盖 `MLX_BASE_URL`，因此 API 用代码默认 `http://127.0.0.1:8081`，聊天 URL 为 `http://127.0.0.1:8081/v1/chat/completions`。`mlx.py` 只允许环回和 `host.docker.internal`。

本地 Vite（`:7777`）把同一组 API 路径代理到 `8787`，`timeout` 和 `proxyTimeout` 都是 0。这只影响本机开发页，不影响公网。

## 4. 请求链

```
浏览器
  → DNS
      本机解析器：198.18.13.138（Clash fake-ip）
      dig @8.8.8.8：175.24.134.228
      dig @223.5.5.5：超时（NOT OBSERVED）
  → TCP/TLS :443
      本次 curl 停在假 IP，VPS 边缘 NOT OBSERVED
      若按仓库 nginx：静态页在 VPS；API 才到 127.0.0.1:17777
      若按仓库 Caddy：API 到 VPS 127.0.0.1:8787（与当前 -R 17777 不是同一端口）
  → SSH -R（本机可见，VPS 监听 NOT OBSERVED）
      公网 API：VPS 127.0.0.1:17777 → Mac 127.0.0.1:8787
      并行、README 公网页不用：VPS 127.0.0.1:8081 → Mac 127.0.0.1:8081
  → Mac FastAPI :8787（private，要登录）
  → httpx → Mac mlx_lm.server :8081
```

`web/nginx.conf` 是另一份 Docker 用的配置（`proxy_pass http://api:8787`，`/chat` 的 `proxy_read_timeout 600s`）。它不是 `kiln.plainlist.space` 这份 vhost。

## 5. 超时（只记文件里写了的）

SSH，来自正在跑的 web-tunnel 命令行和脚本：

| 项 | 值 |
| --- | --- |
| `ServerAliveInterval` / `CountMax` | 15 秒 × 2，对端无响应大约 30 秒后断开 |
| `ConnectTimeout` | 主连接 15 秒；管理员复查 8 秒 |
| `ExitOnForwardFailure` | yes |
| 打开后的复查周期 | 15 秒；远程 `17777` 的 socket 超时 2 秒 |
| 路由未就绪最多等 | `ROUTE_WAIT_S` 默认 45 秒，然后拒绝建立转发 |
| 本机 API 端口预检 | 2 秒 |
| VPS `:22` 预检 | 3 秒 |

mtplx plist（PID 29156 与此一致）：`ServerAliveInterval=30`，`ServerAliveCountMax=3`（大约 90 秒），`ExitOnForwardFailure=yes`，`BatchMode=yes`。没有 `ConnectTimeout`，也没有 `ThrottleInterval`。web-tunnel / api / mlx / web 的 `ThrottleInterval` 是 15 秒。

nginx 仓库 vhost 里写明的 `proxy_read_timeout`：

| location | 值 | 其它 |
| --- | --- | --- |
| `/auth` | 60s | |
| `/chat` | 3600s | `proxy_buffering off`，`proxy_request_buffering off` |
| `/models`、`/generate`、`/v1/` | 3600s | `/v1/` 同样关闭请求缓冲 |
| `/conversation`、`/context`、`/memory` | 文件里没有 | 现网生效值 **NOT OBSERVED** |
| `/`、`/health` | 不反代 | |

整份 vhost 没有 `proxy_connect_timeout`、`proxy_send_timeout`，也没有 server 级 `proxy_read_timeout`。Caddyfile 没有 transport timeout；只有 `flush_interval -1`（流式刷出，不是超时）和 `request_body max_size 12MB`。

API → MLX（`backend/app/config.py` 默认，`api.env` 未覆盖）：`mlx_timeout_s=600`，`mlx_connect_timeout_s=5`。`mlx.py` 把它们交给 httpx：读超时 600 秒，连接 5 秒。SSE 心跳 `heartbeat_s=15`。会话空闲 45 分钟、绝对 12 小时，这是登录态，不是代理读超时。uvicorn 启动参数没有 timeout 标志。

因此在「仓库 nginx 就是现网」这一未证实的前提下，`/chat` 的 3600 秒比 MLX 的 600 秒更长，先到期的会是 API 到 MLX 的 httpx，而不是这份 nginx 的 `proxy_read_timeout`。`/conversation` 等未写超时的 location 不能这么说。现网文件未核对，所以这只是仓库配置的比较，不是一次实测。

本次 curl 自己的上限是 `-m 8`。实际 `time_connect=0.002003`，`time_appconnect=0`，`time_starttransfer=0`，`time_total=0.805348`，`http_code=000`。

## 6. 那一次公网探测

`curl -sS -m 8 -D - -o /dev/null https://kiln.plainlist.space/`

- 错误：`LibreSSL SSL_connect: SSL_ERROR_SYSCALL`（curl 35）
- `remote_ip=198.18.13.138`，不是 `175.24.134.228`
- 没有响应头，没有 Server，不是 401
- 连接耗时 2 毫秒，符合连到本机 Clash 假 IP，而不是连到 VPS

所以：DNS 这一跳被 Clash 改写；TLS/HTTP 边缘、nginx 或 Caddy、隧道往返、MLX，全部 **NOT OBSERVED**。没有做 `--resolve` 的第二次请求。`GET /` 在两份边缘配置里都是静态文件，即便到达 VPS 也不经过 SSH 或 MLX。公网 `/health` 在两份配置里都是直接 404，同样不进隧道。

## 7. Clash / TUN

两个条件都在：ClashX Pro 在跑，`utun4` 为 UP 且地址 `198.18.0.1/16`；Kiln 脚本里有明确的路由规则。

`ensure-vps-direct-route.sh` 拒绝把 VPS 的 `/32` 放到 `utun*` 或网关 `198.18.*` 上，要求物理网卡上的 UGHS 主机路由。`run-web-tunnel.sh` 在打开 `-R` 之前只做 `--check`，最多等 45 秒，不满足就退出，避免经 TUN 留下僵尸转发。

`com.kiln.vps-direct-route` 已经是 system LaunchDaemon（`StartInterval` 20 秒，参数 `--apply`）。本次没有启动它。`launchctl print`：`runs=21248`，上次退出码 0。21:00 前后的路由是 `175.24.134.228 → 192.168.43.1 en0 UGHS`。默认路由也是 `en0`，不是 utun。SSH 到字面 IP 因此走物理网卡，并且当前是 ESTABLISHED。

风险在名字不在这条主机路由：系统 `getaddrinfo` 仍返回 `198.18.13.138`，所以按主机名访问公网页会进 Clash，而按 IP 走的 SSH 不会。日志里隧道累计大量 `remote port forwarding failed`（web 2997 次、8081 方向 17563 次）和 303 次 `REMOTE_LISTENER_LOST`。这些是日志文件里的累计行，没有逐行时间戳，不能当成「今天的次数」。stderr 的 mtime 是今天 20:57，说明失败记录一直追加到这次重启之前。

## 8. 故障类

「本地生成成功，但经 VPS 的请求超时」：**UNTESTED**。

没有向 MLX 或 `/chat` 发送生成。公网 `GET /` 在 TLS 之前就失败在 Clash 假 IP 上，`time_total` 0.8 秒不能当成 VPS `proxy_read_timeout` 或 SSH `ServerAlive` 的证据。本地 `:8787/health` 和 `:8081/health` 也没有请求。
