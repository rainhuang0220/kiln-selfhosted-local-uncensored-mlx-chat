# A15：集成、测试与回滚

日期：2026-09-24。只读核对，没有提交、推送、切换分支，没有改应用代码，没有重启服务，没有发推理请求，也没有跑测试。仓库没有 Makefile。pytest 标记只用了约 10 秒的检索：没有 `gpu` / `live` / `slow` 标记，只有 `pytest.mark.asyncio` 和 `pytest.mark.parametrize`。

本分支相对本地 `main` 只多出账号菜单界面。推理改动已经在历史上。现在不要把 `feat/conversational-reliability` 再合并一次。

## 1. Git

`git status -sb`：`ui/account-menu-placement...public/ui/account-menu-placement`，没有 ahead/behind。HEAD `0a4322de9a506b54411af2ed10f8c081e73ba003`（`0a4322d`，Place the account menu above the sidebar footer.）。已跟踪文件干净。唯一脏内容是未跟踪的 `engineering/`，见第 5 节。

`git log -15 --oneline`：

- `0a4322d` Place the account menu above the sidebar footer.
- `a409fca` Merge pull request #4 from rainhuang0220/ui/sidebar-footer
- `94286f5` Redesign sidebar footer and account controls.
- `e3aceb0` Merge pull request #3 from rainhuang0220/ui/login-visibility
- `ba19d58` Fix login form visibility and auth UX.
- `99f7c6a` Merge pull request #2 from rainhuang0220/security/explicit-exposure
- `66ff5a7` Make exposure an explicit config and add local password recovery.
- `99e7930` Merge pull request #1 from rainhuang0220/security/private-mode
- `658f509` Run verify from the repository root.
- `da2aac8` Run frontend tests from the repo root in CI.
- `7aae70a` Keep Ubuntu CI from parking injected TestClient chat.
- `3f45b7e` Tighten local-open to loopback and cut the public tunnel over to a dedicated SSH user.
- `dd8244a` Close public fail-open and stop serving Vite on the internet.
- `cbbaa6e` fix(chat): harden continuation and long-dialogue cache for RC2
- `a6a4d2e` feat(inference): improve streaming integrity and dialogue continuity

`git cat-file -t`：`cbbaa6e` 和 `a6a4d2e` 都是 `commit`，且都是 HEAD 的祖先。没有 checkout。

`cbbaa6e`（完整 `cbbaa6eab76d42b02025b0ba58b824f3e3bc2dad`）主题是 `fix(chat): harden continuation and long-dialogue cache for RC2`，时间 `2026-09-11 17:36:17 +0800`，作者 rainhuang0220。它把 Interactive Dialogue 的续写收成 tokenizer 原生前缀，只在超预算时折叠，并避免 Continue/Regenerate 出错时清掉上一轮。版本说明仍写 0.6.0 RC。这个提交没有 AI trailer。它同时塞进了续写、折叠、质量指标和 `benchmarks/dialogue_reliability/` 的实机脚本，所以不能当作以后的提交粒度。

`a6a4d2e`（`2026-09-11 14:18:29 +0800`）主题是 `feat(inference): improve streaming integrity and dialogue continuity`。正文带有 `Co-authored-by: Cursor <cursoragent@cursor.com>`。在 `a6a4d2e^..HEAD` 里只看到这一条此类 trailer。它把 SSE、对话折叠、采样、文档和 bench 脚本打在同一个提交里。

其他相关指针：本地 `main` 停在 `e3aceb0`，相对 `public/main`（`cdc6965`，Merge pull request #5）落后 4 个提交，那 4 个是 `cdc6965`、`0a4322d`、`a409fca`、`94286f5`。`feat/conversational-reliability` 停在 `cbbaa6e`，已经包含在当前 HEAD 里。不要为了“集成推理分支”去合并或 checkout。

## 2. 测试怎么跑

没有 Makefile。文档和 CI 都把整套检查写在根目录 `npm test`。

根 `package.json`：

```text
bash tests/test_web_tunnel.sh
&& bash tests/test_vps_direct_route.sh
&& bash tests/test_fetch_model.sh
&& bash tests/test_activate_model.sh
&& (cd backend && ../.venv/bin/pytest -q)
&& npm test --prefix web
```

后端：`backend/pyproject.toml` 的 `[tool.pytest.ini_options]` 只有 `asyncio_mode = "auto"`、`testpaths = ["tests"]`、`pythonpath = ["."]`。开发依赖是 pytest、pytest-asyncio、respx。没有自定义 marker，因此没有文档化的 `-m unit` 快子集。`backend/tests/` 现有 43 个 `test_*.py` 加 `conftest.py`。`README.zh.md` 仍写“后端当前约 29 个测试”，这句已经过时，留给以后的文档提交，不要为了改这一句去跑套件。

这四个 shell 测试不连生产端口。`test_web_tunnel.sh` 和 `test_vps_direct_route.sh` 只做 `bash -n` 和静态检查。`test_fetch_model.sh`、`test_activate_model.sh` 只跑 `--dry-run`。它们不加载权重。

前端：`web/package.json` 的 `test` 是 `vitest run`。`web/vite.config.ts` 把 Vitest 环境设成 `node`。会进这套的是 `stream.test.ts`、`AuthGate.test.tsx`、`SidebarFooter.test.tsx`、`placeAccountMenu.test.ts`、`profiles.test.ts`、`chat-store.test.ts`。`web/src/lib/markdown.node-test.mjs` 的文件名不是 `*.test.*`，不在 `npm test` 里。

CI（`.github/workflows/ci.yml`，Ubuntu 24.04，无 Metal）在 `npm test` 的拆开步骤之外还有：`uv lock --check`、`uv sync --frozen --extra dev`、`npm run build`、Caddy 配置校验、`bash scripts/check-public-tree.sh`。CHANGELOG v0.6.2 写明：注入的 TestClient 不再走真 MLX restore；缺 tokenizer 或缺 mlx 的测试会 skip。所以 Ubuntu 上的 `uv run pytest -q` 是不需要 GPU 的全量门禁。

本机没有跑。原因是这里装了 mlx，`test_media_runtime.py` 会 `pytest.importorskip("mlx")` 然后导入 `mlx.core`；`conftest.py` 把 tokenizer 路径指到仓库上一级的 `qwen3.8-27b`，目录在的话 `test_continue_template.py` 会读本地 tokenizer。这不是文档里的无 GPU 快子集。`benchmarks/dialogue_reliability/run_*.py` 和 `run_prompt_cache_ab.sh` 不在 `npm test` 里，会打到真模型；后者还会 bootout `com.kiln.mlx`。在 `engineering/2026-09-24/ALLOW_BENCH` 出现之前不要跑。

以后总控可以单独跑、且按源码不会加载权重的检查，仅限那四个 shell，以及不 import mlx 的 pytest 文件（SSE：`test_sse_frames.py`、`test_malformed.py`、`test_stream_protocol.py`、`test_stream_termination.py`；压缩：`test_compress.py`、`test_dialogue_context.py`、`test_dialogue_checkpoints.py`、`test_dialogue_harness.py`；生命周期假对象：`test_chat_lifecycle.py`）和 `npm test --prefix web`。这次都没有执行。不要在这台机器上把 `npm test` 当成无模型命令。

API 的 LaunchAgent 用的是 `python -m uvicorn`，没有 `--reload`。后端提交在 kickstart API 之前不会进 PID 15068 那一档进程。本机网页是 Vite 开发服务器，工作目录就是这个仓库，改 `web/src` 可能热更新 `127.0.0.1:7777`。公网是 VPS 上的 `web/dist` 加只反代到 Mac `:8787` 的隧道，不是这条 Vite。公网 Compose（`deploy/compose.yml`）把 `MODEL_DOWNLOADS_ENABLED` 和 `MODEL_SWITCH_ENABLED` 设为 false。集成时不要改公网鉴权，也不要为了本分支去发布静态文件。

## 3. 部署、切换、回滚

仓库没有单独的 rollback 手册。操作面在这些文件里：

- `scripts/install-mlx-launchd.sh`：写 `~/Library/Application Support/kiln/start-mlx.sh` 和 `~/Library/LaunchAgents/com.kiln.mlx.plist`，然后 bootout、bootstrap、kickstart -k。它写的包装脚本是 `exec` 仓库里的 `scripts/start-mlx.sh`。
- `scripts/install-local-runtime.sh`：只装 `com.kiln.api`（`:8787`）和 `com.kiln.web`（`:7777`），注释写明不替换 `com.kiln.mlx`。同样是 bootout 后 kickstart。
- `scripts/install-web-tunnel.sh`：`com.kiln.web-tunnel`，把 VPS `127.0.0.1:17777` 转到本机 `127.0.0.1:8787`。不替换 mlx。
- `scripts/install-vps-direct-route.sh`：系统 LaunchDaemon，给隧道绕过 Clash TUN。
- `scripts/activate-model.sh`：原子写入 `data/active-model.env` 后立刻 `launchctl kickstart -k`。没有旁路端口。`--dry-run` 不重启。
- `backend/app/services/models.py` 的 `activate()` 调上面这个脚本，成功后状态是 `restarting`。
- `backend/app/services/media_runtime.py`：`pause_mlx` 先 bootout，再等 `:8081` 松开（最多 30 秒）；`restore_mlx` 仍是先 bootout，再 bootstrap plist，再 kickstart -k，然后等健康检查。bootout 抢在 kickstart 前面时，launchd 会停在 spawn scheduled，这是回滚时要核对的状态，不是现在代码已经修掉的路径。
- `benchmarks/dialogue_reliability/run_prompt_cache_ab.sh`：bootout 生产 agent，`pkill -f 'python -m mlx_lm.server'`，在 **8081** 上起实验进程，EXIT trap 再拉回 LaunchAgent。这不是旁路演练。KeepAlive 还在时 pkill，会和正在加载权重的新进程叠在一起。

`npm run start:local` 等于 `install-local-runtime.sh`。`npm run dev` / `scripts/dev.sh` 是前台 API+网页，不负责模型进程。

### 现网和仓库不是同一条命令

A2 在 2026-09-24 20:57–20:58 CST 的原始记录（本代理没有再探端口）：

- `gui/501/com.kiln.mlx` 状态 running，pid 1581，runs=6，KeepAlive，ThrottleInterval 15，工作目录是本仓库。上次终止信号是 SIGTERM。已运行约 13 天，启动时间约 2026-09-11 19:50。
- 监听：Python 1581 在 `127.0.0.1:8081`；node 97771 在 `127.0.0.1:7777`；另有 ClashX 在 `198.18.0.1:7777`；Python 15068 在 `127.0.0.1:8787`。这份摘录没有探测 8082，不能当成 MTPLX 没在跑。
- `footprint`：Python 1581 约 5086 MB，其中 IOAccelerator 约 4872 MB。权重目录 `qwen3.5-9b-hauhau-aggressive-mxfp4` 约 5.3G。A6 记录的 Metal 建议工作集约 17.76 GiB，机器统一内存 24GB。
- 进程实际参数：`--temp 1.0 --top-p 0.95 --top-k 20 --prompt-cache-size 4 --prompt-cache-bytes 4G --chat-template-args {"enable_thinking":false,...}`，模型是上面的 9B mxfp4。venv 是 mlx-lm 0.31.3 / mlx 0.32.1。

正在执行的包装脚本是 `~/Library/Application Support/kiln/start-mlx.sh`。它把上述 argv **写死**，并不是 `exec` 仓库脚本。仓库 `scripts/start-mlx.sh` 自 `1d2d688`（2026-09-10）起是 `--temp 0.6`，缓存也是 4 / 4G，另外会 source `data/active-model.env`。因此：

- 只 `kickstart -k` 现有 agent，下一次拉起的是包装脚本里的 **temp 1.0**。
- 再跑一遍 `install-mlx-launchd.sh` 会把包装脚本改成 `exec` 仓库脚本，下一次拉起变成 **temp 0.6**，还会跟着 `MODEL_PATH` 走。这是行为切换，不是原样重装。
- 文档彼此也不一致：`docs/architecture.md` 和 `docs/推理说明.md` 仍写 cache size 3、1G，以及 temp 1.0 或 27B 启动示例；`docs/inference-mlx.md` 一处写 Kiln 用 3/1G，另一处又说默认 10 已经写进 `start-mlx.sh`；`BENCHMARK.md` 说 3/1G 已经落地。现网和仓库脚本都是 4/4G。文档提交不能顺便改启动脚本。

`scripts/com.kiln.mlx.plist` 被 `.gitignore` 忽略，内容是本机路径的副本。不要 `git add -f`。真正生效的是 `~/Library/LaunchAgents/com.kiln.mlx.plist`。

### 安全切换：先测端口，再受控切换

两份 MLX 权重不能叠在这台 24GB 机器上。现驻进程已经占约 5.1GB GPU 足迹，缓存预算还有 4G；再起一个 `mlx_lm.server` 会再映射一份 9B。`BENCHMARK.md` 写明 24GB 上不要同时加载 27B mlx-lm 和 MTPLX。视频路径默认 `pause_chat_for_video=True`，就是为了先放掉聊天进程再加载另一套 MLX 权重；图像默认不停车。`run_prompt_cache_ab.sh` 的 pkill 与 KeepAlive 竞态，是“两个进程同时吃权重”的现成反例。

顺序：

1. 先测现网端口，不起第二个进程。只对 `http://127.0.0.1:8081/v1/models` 做 GET，必要时再看 API `GET /health`。不要发聊天或生成。确认 8081 上只有一个 mlx 进程。这一步失败就不要切换。
2. 要验证新命令行时，选一个空闲的 loopback 端口，避开 8081、7777、8787、17777，也不要假设 8082 空闲。候选进程必须在生产进程已经退出之后才启动。总控先 `launchctl bootout gui/501/com.kiln.mlx`，按 `pause_mlx` 的方式等到 8081 不再监听、PID 1581 消失。不要在 KeepAlive 仍加载时 pkill。
3. 在旁路端口起候选，只做 `/v1/models`。通过后先停掉候选，确认进程和端口都没了，内存足迹下来了，再切生产。
4. 受控 cutover 只做一次：若要保持今天的线上行为，不要重写 Application Support 包装脚本，对现有 agent `kickstart -k` 一次。若故意改 flags，先换包装脚本（或让它 `exec` 一份明确的命令），再 kickstart 一次。不要同时跑 `install-mlx-launchd.sh`、`activate-model.sh` 和实验脚本。
5. 切完再测 8081 的 `/v1/models`，以及 8787 的 `/health`。不要为了 MLX 去重启 `com.kiln.api`、`com.kiln.web`、`com.kiln.web-tunnel` 或 VPS 路由。隧道打的是 8787，MLX 宕的时候公网聊天会失败，但不应靠改鉴权来“修”。
6. `launchctl print` 若不是 running（包括历史上的 spawn scheduled），先 bootstrap 现有 plist，再 kickstart 一次。这是 `restore_mlx` 和 `install-web-tunnel.sh` 已经在用的补救，不是连续 bootout。

回滚目标是 Application Support 里那份冻结 argv（temp 1.0、9B 路径、cache 4/4G、thinking 关），不是 `git checkout` 出来的 `scripts/start-mlx.sh`（temp 0.6）。切换前把包装脚本和 `data/active-model.env` 复本留在仓库外。失败时：确认旁路进程已死，恢复那份包装脚本，再 kickstart 一次，然后重测 8081。不要用 `run_prompt_cache_ab.sh` 当回滚工具。Git 回滚用新的 `git revert`，不要 `reset`、不要 checkout 去改工作区。本地 `main` 是旧的，切过去会让 Vite 和工作目录上的脚本指向另一截历史，而 launchd 的 cwd 就是这个目录。

界面三个提交已经在 `public/main` 的合并 `cdc6965` 里。回滚菜单不是今天的事；要回也是以后对那个合并做 revert，而不是在这台机器上 reset。

## 4. 以后的提交拆分

现在不提交。`a6a4d2e` 和 `cbbaa6e` 已经把下面几类混在一起，不要改写历史。以后总控另起提交时拆开，顺序是文档、SSE、压缩、bench 脚手架，最后才是 launchd。前四类不改 `scripts/start-mlx.sh`，也不重写 Application Support 包装脚本。

项目约束（先前用户指令，不是这次新发明的）：以后这些提交不要加 AI attribution trailer，包括 `Co-authored-by: Cursor <cursoragent@cursor.com>`。`a6a4d2e` 是反例。不要 `git add engineering/`，不要 `git add -f` 被忽略的 plist、`data/`、`benchmarks/**/runs/` 或图片视频。

1. 文档。`README.md`、`README.zh.md`、`CHANGELOG.md`、`MODEL.md`、`SECURITY.md`、`BENCHMARK.md`、`BENCHMARK.zh.md`、`docs/`。要写明：现网包装脚本是 temp 1.0 和 cache 4/4G；仓库 `start-mlx.sh` 是 temp 0.6；文档里的 3/1G 和“默认 10”都是陈旧说法。顺手更正“约 29 个测试”，以及根 `package.json` / `web/package.json` 的 0.6.8 与 `backend/pyproject.toml` 的 0.6.5 不一致。本提交零重启。
2. SSE。只动线上帧分类：`backend/app/providers/sse.py`、`backend/app/services/stream_protocol.py`、`backend/app/services/heartbeat.py`，以及 `test_sse_frames.py`、`test_malformed.py`、`test_stream_protocol.py`、`test_stream_termination.py`、`test_heartbeat.py`、`test_heartbeat_proxy.py`、`web/src/api/stream.ts`、`web/src/api/stream.test.ts`。不要把对话折叠或 `chat-store.ts` 的续写 UI 放进这一笔。API 要等单独的 API kickstart 才生效；在那之前用上面的假对象测试，不要打 8081。
3. 压缩 / 折叠。`backend/app/services/compress.py`、`dialogue_context.py`、`dialogue_checkpoints.py`，以及只服务折叠预算的测试：`test_compress.py`、`test_dialogue_context.py`、`test_dialogue_checkpoints.py`、`test_dialogue_harness.py`、`test_long_conversation.py`。不要把 `engineering/2026-09-24/raw/A8/` 里的 LLMLingua `prompt_compressor.py`、`DOCUMENT.md`、`Code.ipynb` 收进产品树。
4. Bench 脚手架。`benchmarks/dialogue_reliability/` 里的 `run_*.py` 和 `summarize_quality.py`。不要提交 gitignore 的 `runs/`。`run_prompt_cache_ab.sh` 会 bootout 生产 agent，不要放进“只是脚手架”的提交；若以后要留它，放进下一笔并在脚本外写明禁止在 8081 仍被占用时执行。
5. Launchd 探针 / 切换。`scripts/start-mlx.sh`、`scripts/install-mlx-launchd.sh`、`scripts/activate-model.sh`，以及 `media_runtime.py` 的 park/restore/`_port_open` 和对应测试（`test_media_runtime.py` 的端口假对象、`test_chat_lifecycle.py`、`tests/test_activate_model.sh`）。这一笔才会改变下一次重启。落地时走第 3 节的旁路端口，而不是直接重跑 installer。不要把隧道和 VPS 路由安装脚本算进 MLX 探针提交。

## 5. 不许动的未提交内容

应用代码、plist 和启动脚本在这次查看时没有本地修改。脏的全是未跟踪的 `engineering/2026-09-24/`。`engineering/` 不在 `.gitignore` 里，`git add -A` 会把其他代理的报告和原始日志一起收进去。不要 `git clean`，不要还原这些文件。本代理只新增本报告和 `raw/A15/`。

下面是写报告前最后一次 `git status --porcelain=v1 -uall`。之后其他代理还可能继续落文件，那些同样不能删：

- `engineering/2026-09-24/COORDINATION.md`
- `engineering/2026-09-24/agents/A1-macos-hardware.md`
- `engineering/2026-09-24/agents/A6-engine-comparison.md`
- `engineering/2026-09-24/raw/A1/`：`01-os-cpu.txt` 至 `20-venv-imports.txt`（20 个文件）
- `engineering/2026-09-24/raw/A13/`：`00-hf-help.txt`、`01-runtime.txt`、`02-models-root-du.txt`、`03-symlink-sample.txt`、`04-hf-cache-ids.txt`、`04-hf-cache-ls.err`、`04-hf-cache-ls.json`、`05-hf-cache-warnings.txt`、`06-hf-cache-tree.txt`、`07-candidates.txt`、`08-disk-and-stubs.txt`、`09-mtplx-and-apfs.txt`、`10-dry-run-NOT-APPROVED.txt`、`11-usage-and-a12.txt`、`manage-cache.md`
- `engineering/2026-09-24/raw/A14/`：`cli-verify.txt`、`skill-rows.json`、`skills-inventory.json`
- `engineering/2026-09-24/raw/A2/`：`00-meta.txt`、四份 `01-launchctl-*`、`01-launchctl-list.txt`、`01-launchctl-mlx.txt`、`01-launchctl-vps-direct-route.txt`、五份 `02-plist-*`、`03-env-names.txt`、`03-ps.txt`、`04-lsof-listen.txt`、`04-lsof-model-files.txt`、`05-footprint.txt`、`05-lsof-err.txt`、`05-lsof-full.txt`、`05-lsof-model-matches.txt`、`05-model-dir.txt`、`06-err-tail80.txt`、`06-err-tracebacks.txt`、`06-http-summary.txt`、`07-curl-headers.txt`
- `engineering/2026-09-24/raw/A6/`：`01-mlx-version.txt`、`02-mlx-server-help.txt`、`03-mlx-generate-benchmark-flags.txt`、`04-llama-cpp-absent-and-build.md.txt`、`05-gguf-and-memory.txt`
- `engineering/2026-09-24/raw/A8/`：`Code.ipynb`、`DOCUMENT.md`、`Transparency_FAQ.md`、`prompt_compressor.py`
- `engineering/2026-09-24/raw/orchestrator/`：`probe_short.json`、`probe_short_sse.jsonl`、`probe_warm.json`、`tokenizer_counts.json`

被 gitignore、因此不会出现在 porcelain 里、但同样不能删的运行时数据：`data/`（含 `chat.db` 和 `active-model.env`）、`scripts/com.kiln.*.plist`，以及 Application Support / LaunchAgents 里的现网副本。
