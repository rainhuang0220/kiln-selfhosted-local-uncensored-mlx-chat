# Kiln（窑）

在这台 Mac 上跑本地 **Qwen3.8-27B** 的聊天工作台，体验接近 ChatGPT：多轮、历史、流式、Context 面板、token 统计。

```
浏览器 :5173  →  FastAPI :8787  →  mlx_lm.server :8081  →  qwen3.8-27b/
```

打开：**http://127.0.0.1:5173**

英文原文：`README.md`。更细的说明：

| 文档 | 内容 |
|---|---|
| [docs/架构.md](docs/架构.md) | 为什么这样选前后端、怎么接模型 |
| [docs/推理说明.md](docs/推理说明.md) | KV / 前缀缓存 / 为什么不能投机解码 |
| [BENCHMARK.zh.md](BENCHMARK.zh.md) | 实测 tok/s |
| [docs/记忆层.md](docs/记忆层.md) | 长期记忆怎么扩展 |
| [docs/框架对比.md](docs/框架对比.md) | 和 llama.cpp / Ollama 的对比 |

---

## 现在能做什么

- 连续多轮对话（不是问完就结束）
- 左侧历史：今天 / 昨天 / 更早，搜索、双击改名、删除
- 中间聊天：Markdown、代码高亮、复制、再生成、停止
- 右侧 Context：真正发给模型的 system + 历史 + token 占用条
- 每条消息的 ↑输入 / ↓输出 token
- 默认**白底黑字粉强调**，左下角可切 Light / Dark / System
- 长期记忆接口已接 SQLite（不会自动把模型胡话写进记忆）

---

## 端口（这台机器上）

`:8000`、`:3000`、`:8080` 已被别的软件占用，所以 Kiln 用：

| 服务 | 端口 |
|---|---|
| 网页 | **5173** |
| 后端 API | **8787** |
| 模型 mlx_lm.server | **8081**（27B，~6.6 tok/s） |
| 可选 MTPLX | **8082**（默认 4B，本机 ~52 tok/s） |

模型由 LaunchAgent `com.kiln.mlx` 常驻（登录后自动拉起，崩溃会重启）。网页和 API 开着、模型还在加载时，左下角会显示「模型离线，正在重连」。

公网部署使用独立账号：密码只以 Argon2id 哈希保存，浏览器持有随机 session，数据库中同样只保存其哈希；对话按账号隔离。首次账号由私有 `deploy/.env` 中的 `BOOTSTRAP_USERNAME` 与 `BOOTSTRAP_PASSWORD` 创建，默认禁止开放注册。

公网必须走 HTTPS。将 `deploy/.env.example` 复制为不入库的 `deploy/.env`，填写域名、ACME 邮箱和强密码，确保 80/443 可从公网访问，再执行：

```bash
docker compose -f deploy/compose.yml --env-file deploy/.env up -d --build
```

部署使用 Caddy 自动签发、续期 TLS 证书。不要暴露 API 端口，也不要提交 `.env`、数据库、证书或运行时数据。

---

## 怎么启动

必须用 **Python 3.12**，不要用 3.14。  
3.14 会在导入 MLX 时因重复 OpenMP 直接闪退（系统弹「Python 意外退出」）。

```bash
cd kiln

# 只需做一次
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python mlx mlx-lm -e "./backend[dev]"
npm install
npm install --prefix web

# 终端 A：模型（Metal，不能进 Docker）
npm run start:mlx

# 终端 B：网页 + API
npm run dev
```

不要直接敲系统里的 `mlx_lm.server`（那是 Homebrew 绑在 3.14 上的）。一定要用上面的 `npm run start:mlx`。

---

## 速度预期（M4 24GB）

27B 4bit 权重约 **14 GB**。实测（思考关闭）：

| 指标 | 数字 |
|---|---|
| 解码速度 | 约 **5–7 token/秒**（第一次约 4.9，缓存命中后再测约 7.1） |
| 首字时间 | 第一次可能十几秒（Metal 预热） |
| 前缀缓存 | 第二次相同请求 `cached_tokens = 111 / 112`，说明跨 HTTP 请求的缓存是真的 |

这不是网页卡，是这颗稠密 27B 在 24GB 上的正常带宽。流式输出只让字一个个出来，**不会让 tok/s 变快**。

---

## API 一览

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/chat` | 产品聊天（`stream: true` 为 SSE） |
| POST | `/chat` + `regenerate: true` | 重生成上一轮助手回复 |
| GET | `/conversation` | 历史列表，`?q=` 搜索 |
| GET | `/conversation/{id}` | 完整对话 |
| GET | `/conversation/{id}/context` | 上次真正发给模型的快照 |
| GET | `/context` | 全局窗口预算 |
| PATCH | `/conversation/{id}` | 改标题 |
| DELETE | `/conversation/{id}` | 删除 |
| GET/POST | `/memory` | 长期记忆 |
| POST | `/v1/chat/completions` | OpenAI 兼容（给以后的 Agent） |
| GET | `/health` | 模型是否在线 |

---

## 测试

```bash
npm test
```

后端当前约 29 个测试。

---

## Docker

`docker compose up --build` 只起 **API + 网页**。模型必须在 Mac 宿主机上 `npm run start:mlx`（Linux 容器里没有 Metal）。
