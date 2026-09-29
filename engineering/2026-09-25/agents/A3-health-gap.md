# `/health` 不看生成线程

只读核对。未改源码、未重启、未 POST，也未请求 `/health`。

安装的是 Kiln `.venv` 里的 mlx-lm **0.31.3**（mlx 0.32.1）。文件：

`/Users/rainhuang/Desktop/models/kiln/.venv/lib/python3.12/site-packages/mlx_lm/server.py`

（mtime 2026-08-23 01:05:39，早于当前进程启动。）

## `handle_health_check` 不检查生成线程

`do_GET` 在路径正好是 `/health` 时直接调用它，没有别的条件：

```1620:1641:/Users/rainhuang/Desktop/models/kiln/.venv/lib/python3.12/site-packages/mlx_lm/server.py
    def do_GET(self):
        """
        Respond to a GET request from a client.
        """
        if self.path.startswith("/v1/models"):
            self.handle_models_request()
        elif self.path == "/health":
            self.handle_health_check()
        else:
            self._set_completion_headers(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def handle_health_check(self):
        """
        Handle a GET request for the /health endpoint.
        """
        self._set_completion_headers(200)
        self.end_headers()

        self.wfile.write('{"status": "ok"}'.encode())
        self.wfile.flush()
```

全文件里 `_generation_thread` 只出现在创建、启动和 `join`（451–452、456、459 行）。没有任何 `is_alive()`。健康检查不读线程、不读队列，固定 200 和 `{"status": "ok"}`。

生成线程在 `ResponseGenerator.__init__` 里单独拉起，目标是 `_generate`：

```451:452:/Users/rainhuang/Desktop/models/kiln/.venv/lib/python3.12/site-packages/mlx_lm/server.py
        self._generation_thread = Thread(target=self._generate)
        self._generation_thread.start()
```

`_generate`（688 行起）的 `while not self._stop`（717 行）没有外层 `try`。包住异常的只有 `_tokenize`（737–743 行）和后面的 `load`（805–811 行）。`insert_segments` 在这两段之外：

```776:784:/Users/rainhuang/Desktop/models/kiln/.venv/lib/python3.12/site-packages/mlx_lm/server.py
                    (uid,) = batch_generator.insert_segments(
                        segments=[segments],
                        max_tokens=[args.max_tokens],
                        caches=[cache],
                        all_tokens=[prompt[:prompt_cache_count]],
                        samplers=[_make_sampler(args, tokenizer)],
                        logits_processors=[_make_logits_processors(args)],
                        state_machines=[sm],
                    )
```

这里抛出的异常不会放回 `rqueue`，线程直接结束。HTTP 在另一条路径：`ThreadingHTTPServer.serve_forever()`（1706、1728–1729 行），跑在主线程上。`/health` 不进入 `generate()`（1026–1048 行），所以不会堵在已经没人消费的 `response_queue.get()` 上。

## `/tmp/kiln-mlx.err`

只计 `IndexError` 与 `Starting httpd`。异常行本身没有时间戳；日期取该行之前最近一条带 `YYYY-MM-DD HH:MM:SS` 的服务日志。不摘用户提示。

| 项 | 次数 | 按日 | 最后 |
| --- | --- | --- | --- |
| `IndexError` | 7 | 全部 2026-09-11 | 前序时间戳 2026-09-11 19:50:01,539（日志行 43876） |
| `Starting httpd` | 45 | 2026-08-24×1，2026-09-03×7，2026-09-04×15，2026-09-10×6，2026-09-11×16 | 2026-09-11 19:50:34,791（日志行 43881） |

这 7 次都是 `IndexError: list index out of range`。栈是线程入口 → `mlx_lm/server.py:776` `_generate` → `mlx_lm/generate.py:1646` `insert_segments`。最后一次异常的前序时间戳早于最后一次 `Starting httpd`。该文件在 2026-09-25 02:05:57 仍有写入，但那之后没有新的 `IndexError`，也没有新的 `Starting httpd`。

## PID 1581

| 项 | 值 |
| --- | --- |
| PID | 1581（父进程 1，LaunchAgent `com.kiln.mlx`，KeepAlive） |
| 启动 | 2026-09-11 19:50:33 |
| 命令 | `.venv/bin/python -m mlx_lm.server`（`ps` 里是 Homebrew Python 3.12 的 symlink 目标） |
| 监听 | `127.0.0.1:8081` |
| cwd | `/Users/rainhuang/Desktop/models/kiln` |
| stderr | `/tmp/kiln-mlx.err` |
| 已映射的 mlx | `kiln/.venv/.../site-packages/mlx/` |

启动脚本 `~/Library/Application Support/kiln/start-mlx.sh` 用的就是这个 `.venv`。当前 PID 的启动时刻对齐最后一条 `Starting httpd`，晚于最后一条 `IndexError`。日志不能说明这个 PID 此刻的生成线程已经死了。

## 结论

**能。** PID 1581 上的 `GET /health` 可以在生成线程已死时仍返回 200。

这套 0.31.3 的 `handle_health_check` 不看生成线程。`insert_segments` 的未捕获异常会杀掉 `_generate`，`ThreadingHTTPServer` 继续服务，`/health` 照样写 `{"status": "ok"}`。生成请求则会停在 `response_queue.get()`，直到进程被重启。本次没有打这个端点。
