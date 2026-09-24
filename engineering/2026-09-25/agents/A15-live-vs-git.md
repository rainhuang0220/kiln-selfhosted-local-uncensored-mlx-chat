# 线上进程 vs 磁盘上的 TailStripper

只读核对。未重启、未改代码、未切分支。

## Git

- 分支：`eng/inference-baseline-20260924`
- HEAD：`0111852169bb5c6ecabafd3733706f58a89c01c0`
- 该提交：2026-09-24 21:41:38 +0800，`Fix streamed continuation tails and the local stop label.`
- `git log -S '_held'` 显示 `_held` 只在这一笔进入 `backend/app/services/continuation.py`。
- 工作区对该文件无未提交改动；磁盘内容与 HEAD 一致。

## 磁盘上的 tail 修复

`backend/app/services/continuation.py` **包含** `_held`。`TailStripper` 在构造与清空路径里把 `self._held` 置为 `""`，并在拼接残留尾巴时读写它（约第 74–93 行）。这就是本次 tail 修复。

## 8787 上的 API 进程

| 项 | 值 |
| --- | --- |
| PID | 15068（父进程 1） |
| 监听 | `127.0.0.1:8787` |
| cwd | `/Users/rainhuang/Desktop/models/kiln/backend` |
| 启动 | 2026-09-15 13:08:31（周二） |
| `ps` etime | `09-12:57:50`（9 天 12 小时 57 分，核对时刻约 2026-09-25 02:06） |
| 命令 | `python -m uvicorn app.main:app --host 127.0.0.1 --port 8787 --proxy-headers --forwarded-allow-ips=127.0.0.1` |
| `--reload` | 无。也没有 `--workers`。 |

## 结论

**不能。** 这个进程在不重启的情况下，不可能正在跑新的 `TailStripper`。

它比引入 `_held` 的提交早大约 9 天启动。命令行没有 `--reload`，uvicorn 不会在源文件变更后重新导入模块。进程内存里仍是 2026-09-15 13:08 加载的那份 `continuation`，不是 HEAD / 当前磁盘上带 `_held` 的版本。要让线上跑到这次 tail 修复，必须重启该进程。本次未重启。
