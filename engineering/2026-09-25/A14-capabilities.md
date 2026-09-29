# A14 能力盘点（2026-09-25）

只清点本机已有能力。没有安装包，没有 `npx skills add`，没有 `gh auth`，没有连接新 MCP，没有改配置，没有执行 `hf cache rm` / `prune`，没有打开 `.env` 正文，没有跑会加载权重或 `mlx.core` 的测试。

## finding

Kiln 的可执行测试入口已经在仓库根 `.venv`（Python 3.12.12）里，不在 `PATH` 上的 `python3`（3.14.7）。两套解释器目前报出的 mlx / mlx-lm 发行版号相同，但是 site-packages 各一份，pytest 已经不同，所以不能把系统 Python 当成 `.venv` 的替身。`hf` 1.27.0 可以列缓存，删除类子命令带 `--dry-run` 且默认关闭。相关 skill 与五个已连接 MCP 都已存在；Neon 是 write mode，破坏性工具在本会话暴露着，本次没有调用。

## evidence

现场命令，2026-09-25。版本只做 `import` / `importlib.metadata`，没有加载模型。3.14 上没有 `import mlx`（README 写明 MLX + Homebrew OpenMP 会打掉 3.14）。

### Python

| 解释器 | 路径 | 版本 |
| --- | --- | --- |
| `python3` | `/opt/homebrew/bin/python3` → `/opt/homebrew/opt/python@3.14/bin/python3.14` | 3.14.7 |
| Cellar `python@3.12` | `/opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/bin/python3.12`；`/opt/homebrew/opt/python@3.12` → `../Cellar/python@3.12/3.12.12_2`；`/opt/homebrew/bin/python3.12` 同一条链 | 3.12.12 |
| `kiln/.venv` | 存在。`bin/python` → `/opt/homebrew/opt/python@3.12/bin/python3.12` | 3.12.12 |

`.venv`：`importlib.metadata` 给出 mlx **0.32.1**、mlx-lm **0.31.3**、pytest **9.1.1**。`import mlx` 成功，但没有 `__version__`，`__file__` 为空；`import mlx_lm` 的 `__version__` 是 0.31.3。包位置：`kiln/.venv/lib/python3.12/site-packages`。

系统 `python3`（3.14，只读 metadata，未 import 原生模块）：mlx **0.32.1**、mlx-lm **0.31.3**，位置 `/opt/homebrew/lib/python3.14/site-packages`。pytest **9.0.3**。发行版号此刻与 `.venv` 相同，安装目录不是同一个。`pytest` 不在 `PATH`。

### node / git / hf

| 命令 | 结果 |
| --- | --- |
| `node` | 有。`~/.nvm/versions/node/v24.18.0/bin/node`，v24.18.0。README 要求 Node 20+ |
| `git` | 有。`/usr/bin/git`，2.50.1（Apple Git-155） |
| `hf` | 有。`/opt/homebrew/bin/hf`，`hf version` → 1.27.0 |
| `huggingface-cli` | 文件在 `/opt/homebrew/bin/huggingface-cli`。`--version` 只打印弃用警告：已不能用，改用 `hf`。没有单独的数字版本 |

`hf cache --help` 第一屏有 `list`（别名 `ls`）、`prune`、`rm`、`verify`。第一屏没有 dry-run。`hf cache rm --help` 与 `hf cache prune --help` 都有 `--dry-run / --no-dry-run`，默认 `no-dry-run`。示例是 `hf cache rm model/gpt2 --dry-run` 和 `hf cache prune --dry-run`。这两条 help 之外没有执行 rm/prune/ls。

### 已有 skill（只列目录名）

`~/.grok/skills`：`diagnosing-bugs`、`code-review`、`tdd`、`research`（皆为指向 `~/.mirasim/mattpocock-skills/skills/engineering/…` 的符号链接）。没有名字匹配 verification 或 deja 的目录。

`~/.agents/skills`：`diagnosing-bugs`、`systematic-debugging`、`code-review`、`receiving-code-review`、`requesting-code-review`、`tdd`、`test-driven-development`、`verification-before-completion`、`research`、`deja-history`、`deja-search`。

`~/.grok/bundled/skills`：`code-review`、`review`。没有 debug / tdd / verification / research / deja 目录名。

### 测试命令（未启动套件）

仓库没有 Makefile。真实入口：

- 根目录 `package.json` 的 `npm test`：四个 shell（`tests/test_web_tunnel.sh`、`tests/test_vps_direct_route.sh`、`tests/test_fetch_model.sh`、`tests/test_activate_model.sh`），然后 `(cd backend && ../.venv/bin/pytest -q)`，然后 `npm test --prefix web`。
- `backend/pyproject.toml`：`testpaths = ["tests"]`，`pythonpath = ["."]`，`asyncio_mode = "auto"`。dev 依赖 pytest、pytest-asyncio、respx。没有 gpu/live marker。`requires-python` 是 `>=3.11,<3.14`。
- `backend/tests/` 有 43 个 `test_*.py`。`README.md` / `README.zh.md` 只写 `npm test`；中文 README 的「约 29 个测试」已过时，本次不改文档。
- 前端 `web/package.json`：`vitest run`。
- CI `.github/workflows/ci.yml`（Ubuntu 24.04，Python 3.12，无 Metal）：同一组 shell，外加 `uv lock --check`、`uv sync --frozen --extra dev`，后端是 `uv run pytest -q`，再 `npm test --prefix web`。

本机 `.venv/bin/pytest` 是 9.1.1，所以 pytest 能跑。本次只跑了 `--version`。唯一会拉起原生 MLX 的测试是 `backend/tests/test_media_runtime.py` 的 `test_wan_teacache_module_imports`：`pytest.importorskip("mlx")` 之后 `import wan_teacache`，而 `backend/app/services/wan_teacache.py` 模块级 `import mlx.core`。其余测试里的 “mlx” 是 HTTP/假对象或字符串，不是 `mlx.core`。因此不要把本机全量 `npm test` / `pytest -q` 当成无 GPU 命令。

### 秘密文件

没有打开任何 env 文件，报告里没有 token。

| 路径 | 磁盘 | git |
| --- | --- | --- |
| `deploy/.env` | 存在 | 被 `.gitignore` 第 24 行 `.env` 忽略；`git ls-files` 未跟踪 |
| `.env`、`.env.local`、`backend/.env`、`web/.env` | 不存在 | `git check-ignore` 仍会忽略（`.env` 或 `.env.*`） |
| `.env.example`、`deploy/.env.example` | 存在 | 被 `!.env.example` 与 `!**/.env.example` 重新纳入，且已被跟踪。正文未读 |

### 已连接 MCP（本会话工具表 + 本机文件）

本会话工具表：`cursor`（41）、`deja`（1）、`github`（94）、`neon`（113）、`tasks`（10）。Neon 为 write mode，破坏性工具已暴露。没有调用 Neon，也没有调用其它 MCP 写操作。

磁盘：`~/.grok/user-settings.json` 与 `~/.grok/config.toml` 只启用 deja（`/Users/rainhuang/.local/bin/deja mcp`）以及插件 `superpowers`、`neon`。已装 Neon 插件指向 `https://mcp.neon.tech/mcp`。`~/.cursor/mcp.json` 只有 deja。`cursor` / `github` / `tasks` 在本会话工具表里，不在上述用户 mcp.servers 列表里；没有为此新加配置。`~/.grok/mcp_credentials.json` 含 Neon 凭据，内容未写入本报告。

## proposed change

本阶段不改应用代码、不改配置、不安装。

下一件不需要新安装的事：用已有 `.venv` 跑后端里不碰 `mlx.core` 的 pytest：

```bash
cd /Users/rainhuang/Desktop/models/kiln/backend && ../.venv/bin/pytest -q -k 'not test_wan_teacache_module_imports'
```

不要用 `python3 -m pytest`（那是 3.14 / pytest 9.0.3）。不要跑 `hf cache rm` 或 `prune`，除非显式加上 `--dry-run` 并且另有清理授权。Neon 写操作继续不要调用。

## risk

- `PATH` 的 `python3` 是 3.14.7，超出 `requires-python` 上界。mlx 号现在碰巧一样，两套 site-packages 以后会分叉；pytest 已经分叉。
- `hf cache rm` / `prune` 默认不是 dry-run。不加 `--dry-run` 会删缓存。
- 全量 `../.venv/bin/pytest -q` 会执行 `test_wan_teacache_module_imports`，从而 import `mlx.core`。`benchmarks/dialogue_reliability/run_*.py` 不在 `npm test` 里，会打到真模型；本次没跑。
- Neon write mode 下误调用删除/改库工具会改远端数据。凭据文件已存在，不要抄进工单。
- `deploy/.env` 被忽略但仍在工作区。后续命令不要 `cat` 它。

## tests

盘点当场做了：解释器 `--version`、`.venv` 内 mlx/mlx-lm/pytest 的 metadata 与 import、`hf version`、`hf cache --help`、`hf cache rm --help`、`hf cache prune --help`、`git check-ignore`、env 文件是否存在（不读内容）、skill 目录名。没有跑 pytest 套件、vitest、四个 shell 测试，也没有发推理请求。

以后要证明门禁，用上一节的排除命令；CI 上的无 Metal 全量命令仍是 `backend` 里的 `uv run pytest -q`。

## rollback

没有安装、没有改配置、没有改应用源码。撤回本次盘点只需要删掉本文件：

`engineering/2026-09-25/A14-capabilities.md`

## status

- 盘点（版本、help、skill 名、测试入口、gitignore、已连接 MCP 的只读记录）：`tested_live`
- 任何安装、`npx skills add`、`gh auth`、新 MCP、改配置、`hf cache rm`：`not_done`
