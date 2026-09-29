# 2026-09-25 02:03 CST 现场状态

这一阶段没有改 Kiln 源码，没有重启服务，没有再删文件。数字来自当场命令。

## 此刻五层都通

| 层 | 证据 |
| --- | --- |
| 进程在 | `com.kiln.mlx` state=running，PID **1581**，`runs=6`。不是重启循环 |
| 模型已加载 | `footprint` 5162 MB，峰值 9215 MB。RSS 不能当依据 |
| 能生成 | `POST /v1/chat/completions`，`max_tokens=16`，`temperature=0`，1.984 s，`finish_reason=stop`，正文 `phase1-alive` |
| API 可达 | `127.0.0.1:8787/health` 为 `status=ok`，`inference.ready=true`，`consecutive_timeouts=0`，`chat.state=running` |
| 前端进程在 | node PID 97771 听 `127.0.0.1:7777`。ClashX 另听 `198.18.0.1:7777`，不是同一个套接字 |

机器：24 GiB 统一内存。`kern.memorystatus_level=41`，压力档 2（Urgent）。swap 已用 13098 MiB / 14336 MiB。没有再跑 20k/32k。

Git 在 `eng/inference-baseline-20260924`，HEAD `0111852`。API 是 PID 15068，没有 `--reload`。磁盘上的 `TailStripper` 修复不在这个已运行的进程里。

## 「模型暂时离线」是哪一层

文案在 `web/src/app.tsx`。条件是 `!store.health?.provider.reachable`。

`provider.reachable` 只有一条来源：已登录之后 `loadHealth` 请求 Kiln `GET /health`，后端 `MlxProvider.health()` 再 `GET` mlx 的 `/health`，HTTP 200 才是 true（`backend/app/providers/mlx.py`）。失败或抛错时，store 把 `reachable` 写成 false。

所以这句横幅的意思是：**Kiln API 当时没有从 mlx 拿到 HTTP 200**。它不区分下面几种情况，文案却一律写成 LaunchAgent 会在一两分钟内拉起。

| 实际情况 | 横幅 | 对不对 |
| --- | --- | --- |
| 视频任务调用 `pause_mlx`：`launchctl bootout` 把 8081 停掉，给显存放视频。`restore_mlx` 再 bootstrap/kickstart，最多等 180 秒，并做一次 1 token 冒烟 | 会出现，一两分钟的说法和这段恢复循环一致 | 这是设计出来的离线，不是 LaunchAgent 自己掉了 |
| mlx 正在 KeepAlive 拉起、权重还没听端口 | 会出现 | 对。端口还没有 |
| 生成线程已经死，但 mlx-lm 0.31.3 的 `/health` 仍无条件返回 200 | **不出现** | 假在线。`inference.ready` 也只在连续 3 次用户请求超时之后才变 false |
| Kiln API 自己挂了，`/health` 根本没返回 | 出现，文案仍指责 mlx | 错层 |
| 未登录 | 看不到这句。`app.tsx` 在登录门后才渲染聊天页。`loadHealth` 在未登录时直接 return，不去打 `/health` | 横幅不是登录页的状态 |

`/tmp/kiln-mlx.err` 里最后一批 `IndexError: list index out of range` 在 **2026-09-11 19:50**，紧挨着 `POST /v1/completions`，然后是 `Starting httpd`。那是精确 prompt-cache 命中把 segment 弹空。当前 PID 1581 从那次拉起后一直在，9 月 24–25 日的日志没有新的 IndexError。今晚这次生成成功。

## 优化前的长上下文（2026-09-24，没有优化后）

同一台机器、同一个 9B、没有重启。n=1，除非另注。

| 输入 | 服务器 token | TTFT | 内存 |
| --- | ---: | ---: | --- |
| 20000 个中文字符 | 13476（本地 tokenizer 13464，不是 20000 token） | 65.1 s | footprint 到 7678 MB |
| 20000 token | 20012 | 100.8 s | footprint 到 8018 MB |
| 同一中文题再发一次 | 只重算 4 token | 0.388 s | 缓存命中 |

Decode 中位数 21.4 tok/s（n=3，各 80 token）。没有「优化后」一行。64k 没跑。

## 还没动的技术路线

不在这一阶段改代码。下一阶段要改的是健康检查的定义，而不是把横幅藏起来：

1. 横幅只在「端口没有 200」时出现，生成死掉时它不出现。健康检查要做一次短生成，失败就 503，不能只看端口。
2. 视频 `bootout` 是真离线。恢复失败要和「模型还在加载」分成两句，不能都叫 LaunchAgent 马上拉起。
3. 20k 的 TTFT 大约 200 token/s 的 prefill。Decode 已经贴着 5.3 GB 权重和 M4 带宽。变快要靠前缀缓存命中和少做重复 prefill，不是把 `max_context` 改大。
