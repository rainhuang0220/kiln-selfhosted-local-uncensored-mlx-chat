# 「模型暂时离线」只表示 `provider.reachable` 不为真

文案只在已通过登录门的 **Chat** 视图里渲染。条件是 `!store.health?.provider.reachable`（`web/src/app.tsx:464-467`）。`health` 为 `null`、缺字段，或 `reachable === false` 都会出现。Generate 页（`web/src/app.tsx:271-284`）没有这句。未过 `AuthGate` 时整段聊天壳不挂载（`web/src/app.tsx:146-158`），横幅也不会出现。

这不是「进程已死 / 权重未进内存 / 不能推理」的判定。它只反映 store 里最近一次健康结果的那个布尔，或还没有任何成功结果。

## 布尔从哪来

1. 前端 `loadHealth`（`web/src/stores/chat-store.ts:264-302`）先 `GET /auth/status`。需要登录且未登录则直接 return，**不改** `health`（`:279`）。否则 `GET /health`（开发时由 Vite 转到 `http://127.0.0.1:8787`，`web/vite.config.ts:5-6`、`:40`）。`r.ok` 才把 JSON 原样写入 `store.health`（`:284-287`）。任何抛错（8787 连不上、非 2xx、JSON 坏）走 catch，合成 `provider.reachable: false`（`:288-301`）。合成对象没有 `inference`、没有 `chat`。
2. 刷新：挂载、每 10s、标签页重新可见（`web/src/app.tsx:39-50`），以及登录/注册/激活模型之后（`chat-store.ts:197`、`:230`、`:156`）。
3. Kiln `GET /health` 本身几乎总是 HTTP 200（`backend/app/main.py:295-329`）。`reachable` 初值 `False`（`:298`）；有 provider 时等于 `await provider.health()`（`:299-300`）。`status` 还要 `inference.ready` 才是 `"ok"`，否则 `"degraded"`（`:306-307`）。横幅**不看** `status`、`inference`、`chat`。`http_alive` 与 `reachable` 是同一次赋值（`:312-314`），不是第二次探测。`/health` 对未登录公开（`backend/app/auth.py:138`）。私有模式下 `base_url` 被清空（`main.py:301-302`），横幅也不读它。
4. `MlxProvider.health`（`backend/app/providers/mlx.py:57-63`）只做 `GET settings.mlx_health_url()`，`status_code == 200` 为真，`httpx.HTTPError` 为假。不解析 body，不发 chat completion。默认 URL 是 `http://127.0.0.1:8081/health`（`backend/app/config.py:24`、`:120-124`）。连接超时 5s，读超时跟 `mlx_timeout_s` 600s（`config.py:25-26`，`mlx.py:44-46`）。
5. `:8081/health` 是 `mlx_lm.server` 的 `handle_health_check`：不看 `self.model`，固定 HTTP 200 和 `{"status":"ok"}`（安装包 `mlx_lm/server.py:1626-1640`）。HTTP 在 `ResponseGenerator()` 里先拉起生成线程（同文件 `:451-452`），`load_default()` 在该线程的 `_generate` 开头（`:694-695`），`serve_forever` 与加载并行（`:1735-1746`）。端口已听、`/health` 已 200 时，权重仍可能是 `None`。生成线程若在 `load` 里死掉，HTTP 线程仍会继续回 200。

因此横幅消失只证明：前端这次 `GET /health` 成功，且 Kiln 对 `:8081/health` 拿到了 HTTP 200。横幅出现则是下面三种之一，UI 不区分：

- 登录壳已经画出来，但 `/health` 还没写回（`health` 初始 `null`，`chat-store.ts:78`）。
- Kiln 200 且 `provider.reachable === false`（`:8081` 拒绝连接、超时、非 200，或 provider 缺失）。
- 前端根本没拿到 Kiln 的 `/health`（catch 合成离线）。文案仍写成「Mac 上的 mlx / LaunchAgent」（`app.tsx:466`），**8787 自己挂了也会显示同一句**。

Send 不看这个标志，只看草稿是否为空（`app.tsx:625-628`）。占位符是另一句「模型离线，正在自动重连」（`:492-497`）。侧栏「模型离线 / 正在重连」也是另一处，且 `chat.state !== "running"` 时优先显示「视频生成中」（`web/src/components/SidebarFooter.tsx:14-22`）。连接失败字符串 `mlx unreachable: All connection attempts failed` 走的是 `store.error` 第二条横幅（`app.tsx:469-474`），不是本句。

## `pause_mlx` / `restore_mlx` 不直接改这个布尔

`pause_mlx`（`backend/app/services/media_runtime.py:49-57`）对 `gui/{uid}/com.kiln.mlx` 做 `launchctl bootout`，再等最多 30s 直到 `127.0.0.1:8081` TCP 连不上。不请求 `/health`。视频任务（以及 flux1-dev）在跑生成前调用它（`backend/app/services/media.py:333-338`、`:380-382`；`chat_lifecycle.py:80-85` 在未注入回调时落到 `pause_mlx`）。端口关掉之后，下一次 `provider.health()` 失败，**Chat 页会同时出现**两条横幅：上面是 lifecycle 文案（`app.tsx:288-291`，状态属于 `PARKING|PARKED|RESTORING|RECOVERY_FAILED`，`chat_lifecycle.py:9-19`、`:44-45`），下面仍是「模型暂时离线」。`/chat` 在这些状态直接 503（`main.py:655-665`），与 `/health` 的 `reachable` 无关。

`restore_mlx`（`media_runtime.py:95-113`）`bootout` + `bootstrap` plist + `kickstart -k`，最多等 180s。`_health_ok` 同样只认 HTTP 200（`:60-67`）。接着 `_smoke_chat` 打一 token（`:70-92`）；smoke 失败仍会再看一次 health，200 就 return（`:108-111` 注释写明加载竞态）。smoke 失败**不能**拦住横幅消失。Kiln 启动时若 `pause_chat_for_video` 且 `:8081/health` 不是 200，也会 `restore_mlx`（`main.py:245-259`）。plist 的 `KeepAlive` + `ThrottleInterval` 15（`scripts/com.kiln.mlx.plist:25-28`）只覆盖「job 仍加载着、进程崩溃」；`bootout` 之后要靠 `restore_mlx` 拉回来。横幅那句「一两分钟内自动拉起」把崩溃重启和主动 park 说成了同一件事。

`inference.ready` 是另一条线：连续超时次数 `< 3`（`backend/app/services/chat.py:314-328`）。三次超时后 `/health` 可以 `reachable: true` 且 `status: "degraded"`、`inference.ready: false`（`backend/tests/test_inference_watch.py:1-11`）。横幅照样隐藏。

## 五项

| 命题 | 横幅在（`reachable` 不为真） | 横幅不在（`reachable === true`） |
| --- | --- | --- |
| 进程还活着 | **不能证明已死。** 也可以是 health 尚未返回、8787 失败被合成成离线，或 park 故意 `bootout`。 | **只证明探测当时有进程在 `:8081` 上对 `GET /health` 回了 HTTP 200。** 不证明是 LaunchAgent、不证明生成线程还在、不证明之后还活着。 |
| 模型已加载 | **不能证明没加载。** | **不能证明已加载。** mlx 的 `/health` 不读 `model`；HTTP 与 `load_default()` 并行。 |
| 推理就绪 | **不能证明不能推理。** UI 不读 `inference.ready`。 | **不能证明能推理。** 超时计数、park/restoring、smoke 失败都不进这个布尔。`restore_mlx` 可以在 completion 失败时仍因 200 返回。 |
| API 可达 | **不能证明 8787 或 8081 不可达。** 8787 正常 200 且 `reachable: false` 与 8787 本身失败，是同一句文案。也不等于 `/v1/chat/completions` 失败。 | **证明两条 GET `/health` 当时通了：** 浏览器到 Kiln，以及 Kiln 到 `:8081/health` 且状态码 200。不证明 chat/completions。 |
| 前端能用 | **不能证明前端坏了。** 这句只有聊天壳已经画出来才会出现；Send 不因此禁用。 | **不能证明功能可用。** 登录、Generate、发送 503、流式错误都不由这句覆盖。 |

## 本次各 GET 一次（2026-09-24 18:08:26 GMT）

不改变上面的语义，只说明写报告时横幅会隐藏。

- `http://127.0.0.1:8081/health` → `HTTP/1.0 200`，`Server: BaseHTTP/0.6 Python/3.12.12`，body `{"status":"ok"}`。与 `mlx_lm.server` 的固定健康响应一致，body 里没有模型或加载状态。
- `http://127.0.0.1:8787/health` → `HTTP/1.1 200`，`status: "ok"`，`provider.reachable: true`，`http_alive: true`，`inference.ready: true`，`consecutive_timeouts: 0`，`chat.state: "running"`，`base_url: ""`（私有模式藏了内部 URL）。`http_alive` 与 `reachable` 同值。
