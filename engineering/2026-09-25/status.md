# 2026-09-25 阶段状态

现场复核后做了代码修复，并只重启了 Kiln API。没有重启 MLX，没有发 20K 请求，没有删除任何模型或缓存。

## 现在还在跑的进程

| 进程 | PID | 说明 |
| --- | --- | --- |
| MLX `com.kiln.mlx` | 1581 | 自 2026-09-11 19:50:33 起未重启。监听 `127.0.0.1:8081` |
| Kiln API `com.kiln.api` | 48231 | 回滚演练之后拉起。监听 `127.0.0.1:8787`。代码为 `bff8f28` |
| 前端 vite | 97771 | 仍是原来的进程，工作目录 `kiln/web`。磁盘上的页面代码已到 `46ed972` |

Git 分支 `eng/inference-baseline-20260924`，HEAD `46ed972`。上一笔功能提交是 `bff8f28`。没有 push。

02:55 的 `GET /health`：`status=ok`，`provider.reachable=true`，`gateway.state=AVAILABLE`，`last_verified_at=null`。这只说明新 API 进程还没有记下一笔成功生成。MLX 的 `/health` 仍然只返回 `{"status":"ok"}`。

## 已落地

`bff8f28` 在 `0111852` 之上：

- 坏 JSON 之后即使还有 `finish_reason=stop` 和 `[DONE]`，账本记为 `completed_with_transport_error`，不再记成干净的 stop。正文保留。`model_finish_reason` 与 `transport_integrity` 分开。
- `/chat` 的 SSE 带同一个 `request_id` 和从 1 递增的 `seq`。
- `/health` 保留原来的 `reachable`，并增加 `gateway`：`AVAILABLE` / `BUSY` / `VIDEO_SUSPENDED` / `STARTING` / `DEGRADED` / `OFFLINE`。视频暂停优先于“端口挂了”。健康检查本身不发生成。
- 前端在接口请求失败时标 `API_UNREACHABLE`，不再一律写成模型离线。视频暂停、端口不通、生成异常、队列忙的文案不同。
- `46ed972`：侧栏在 `last_verified_at` 为空时写“端口在线 / 还没有一次成功生成”。

测试：工作树里 backend `pytest -k 'not test_wan_teacache_module_imports'` 为 260 passed、5 skipped。相关前端 vitest 16 passed。这些是单元测试，不是浏览器验收。

## 回滚演练

备份在仓库外：`/Users/rainhuang/Desktop/models/kiln-backups/2026-09-25/`。`chat.db` 用 sqlite `.backup` 得到，`PRAGMA integrity_check` 为 `ok`。同目录有两份 `start-mlx.sh`、五份 LaunchAgent plist，以及 `api.env`（权限 600，未写入 git）。

演练只动了 API：

1. `git switch --detach 0111852`，`launchctl kickstart -k gui/501/com.kiln.api`。健康检查里没有 `gateway`。MLX 仍是 1581。
2. `git switch eng/inference-baseline-20260924`（当时是 `bff8f28`），再次 kickstart。`gateway.state` 回到 `AVAILABLE`。新 API PID 48231。MLX 仍是 1581。

数据库和 MLX 的 LaunchAgent 没有被这套补丁改过，所以没有做还原演练。再退回 API 时重复上面的 detach 和 kickstart 即可。

## 资源与磁盘

A1：swap 两次间隔 16 秒都是 14336M 里已用约 13262M，swapouts 增量为 0，之后还略降。压力档 2（warn）。PID 1581 的 `phys_footprint` 5154 MB，其中约 4879 MB 在图形/交换列，RSS 只有十几 MB。不能做 20K 压测。

A12：Data 卷可用约 406 GiB。9B、27B、Z-Image、FLUX、Wan、HF 里的 Qwen2.5-1.5B 都在。没有找到可称为 Qwen3B 的目录，这不证明学习模型不存在。证据完整、可以删除的条目是 0。本次删除量是 0。上一轮已经删掉的碎片没有再计。

## 验收

| 门禁 | 结果 |
| --- | --- |
| 服务分层 | 部分。gateway 已在 8787 上。回滚演练做过。没有做生成线程死亡注入，也没有真的 bootout 视频暂停 |
| 流式 | 部分。`0111852` 和坏 JSON 修复已随 API 重启进进程。没有浏览器点击 Stop/Continue，没有 UTF-8 fuzz |
| 长输入 20K | 未做。模型工作集在交换区，不能把检索或短回复当成 20K 通过 |
| 速度 | 未做。没有新的冷/热 TTFT。基线仍是 2026-09-24 的 65.1s / 100.8s |
| 压缩 / KV / 换引擎 | 未做 |
| 磁盘清理 | 清单已做，可删项为 0，没有执行删除 |
| 回滚 | API 代码演练过。数据库与 MLX 启动方式未改 |
| 安全 | 没有把密钥提交进 git。8787/8081/7777 仍只绑 127.0.0.1。没有去掉登录 |

公网登录到 Stop 的整段没有在这一轮重测。隧道进程当时在，`127.0.0.1:17777` 转到本机 8787。

## 还不能写成已修复

- mlx-lm 0.31.3 的 `handle_health_check` 仍不看生成线程。`insert_segments` 的空 segment 路径还在。9 月 24–25 日没有新的 IndexError，这不是补丁。
- 当前 API 的 `inference.ready=true` 只表示本进程里连续超时还没到 3 次。`last_verified_at` 仍是 null。
- 真实短生成探针没有接进生产。接进去会把已经换出的约 5GB 拉回来，也可能占掉一条 prompt cache。
- 20K 字符和 20K token 今天都没有再送进模型。
