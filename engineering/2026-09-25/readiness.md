# 2026-09-25 推理就绪与未达标项

代码在 `eng/inference-ready-20260925`，提交 `bdb9bfa` 和 `c7c5c01`。没有重启 MLX PID 1581，没有重启 API PID 48231，没有发送 20K，没有删除文件。运行中的 8787 仍是上一轮加载的代码，直到下一次明确的 API 重启。

## 本轮改了什么

`bdb9bfa` 把端口连通和推理能力分开。`provider.reachable` 仍表示 MLX 的 HTTP 是否返回 200。`gateway.state` 仍使用 `AVAILABLE`、`BUSY`、`VIDEO_SUSPENDED`、`STARTING`、`DEGRADED`、`OFFLINE`。新增：

| 字段 | 含义 |
| --- | --- |
| `inference_capability` | `UNVERIFIED`、`READY`、`BUSY`、`DEGRADED`、`FAILED` |
| `verification_method` | `user_generation` 或 `probe` |
| `last_verified_at` / `evidence_expires_at` | 最近一次成功生成和 15 分钟证据有效期 |

新进程在没有任何成功生成时是 `UNVERIFIED`，顶层 `status` 仍可以是 `ok`，因为端口是通的。一次超时变成 `DEGRADED`。连续三次超时、显式的生成线程死亡或模型卸载变成 `FAILED`。队列忙时能力是 `BUSY`，不会被记成线程死亡。成功的用户生成会把状态打回 `READY`。过期的证据回到 `UNVERIFIED`，不会被记成失败。

`/health` 仍然不发生成。短探针没有接到生产进程。隔离测试用本机临时端口：`GET /health` 返回 200，`POST` 返回 500，状态变为 `FAILED`；把这个临时服务恢复后，下一次探测记为 `probe` 并回到 `READY`。恢复动作的名字是 `restart_backend`，测试没有对 PID 1581 调用 launchctl。

`c7c5c01` 让页面前端按到达顺序接收 SSE。重复序号不追加，跳号不把后面的帧补进正文，另一个 `request_id` 不能把这一轮收成干净的 stop。这些是 Mock SSE，没有打到 MLX。

后端相关测试 13 项通过，全量后端除去会 import MLX 的一项为 266 passed。前端相关 36 项通过。浏览器里没有手点 Stop 或 Continue。公网登录到页面的顺序没有重测。

## 内存，2026-09-25 约 11:30

12 秒内 swap 存量都是 13146.50M / 14336.00M。`Swapouts` 停在 73573783，没有新增换出。`Swapins` 从 53654806 增到 53654830，大约 384 KiB。空闲内存约 40%。这是历史换出还在，不是这一小段里的持续换出风暴。

PID 1581 的 `phys_footprint` 是 5106 MB，其中 IOAccelerator 4887 MB，RSS 只有约 9 MB。RSS 最大的是 Zotero，约 1.5 GB，后面是 Chrome、Cursor、Codex 和 QQ。不能凭这一次 swap 存量指定某一个进程是原因。9B 的工作集仍主要在图形账本里。这个状态下没有跑 20K。基线仍是 65.1 秒、100.8 秒、重复输入 0.388 秒、Decode 中位数 21.4 tok/s。

## 长上下文和磁盘

预算内不改写早期摘要的行为已经在 `test_does_not_fold_under_token_budget_just_because_turns_exceed_target` 和 `test_sealed_checkpoint_text_does_not_rewrite_on_next_fold`。本轮没有再接压缩器或 KV 压缩，也没有新的 20K 保真度数字。

可删项仍是 0。27B 目录还在，测试配置仍指向 `qwen3.8-27b`。没有 dry-run 删除，没有释放空间。

## 还不能称为完成

- 8787 上的进程还没加载 `bdb9bfa`。
- 没有在浏览器里点 Stop、Continue，也没有从公网看 SSE 序号。
- 没有真实短生成，因此生产上的 `last_verified_at` 没有被这轮更新。
- 20K 字符和 20K tokens 没有新的测量。
- mlx-lm 0.31.3 的 `/health` 仍不检查生成线程。隔离测试证明的是 Kiln 自己的状态机，不是给 PID 1581 打过补丁。
