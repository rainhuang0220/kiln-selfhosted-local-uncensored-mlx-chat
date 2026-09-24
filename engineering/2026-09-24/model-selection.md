# 模型选择（2026-09-24）

生产模型没有换。现网仍然是 `start-mlx.sh` 里的 9B mxfp4。

## 留在生产上的模型

`/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4`

README 对应 `TheCluster/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-MLX-mxfp4`，基座 `HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive`。本机 `du` 5.3G。mlx-lm 0.31.3 已经在这条进程上跑了 13 天。架构是 `qwen3_5`：32 层里 24 层线性注意力、8 层全注意力，`max_position_embeddings=262144`，量化 mxfp4 / group 32。

卡片上的「0/465 refusals」是作者声明。这次没有做拒答率统计，不能写成 0。已核实的是：没有在 Kiln 和 mlx-lm 之间再插一层内容审核；模型能答完 20000 字里的三笔金额，也能在 32k token 上开始生成。

官方非思考采样是 temperature 0.7、top_p 0.8、top_k 20。现网 LaunchAgent 是 temperature **1.0**、top_p **0.95**、top_k 20，思考关闭。仓库 `scripts/start-mlx.sh` 写的是 temperature 0.6，而且会读一个并不存在的 `active-model.env`。正在跑的是 Application Support 里那份 1.0，不是仓库脚本。没有为了“对齐推荐值”去重启。

## 不升成默认的已有权重

| 权重 | 体积 | 决定 |
| --- | ---: | --- |
| `~/.mtplx/models/Youssofal--Qwen3.5-4B-MTPLX-Optimized-Speed` | 2.39 GiB | 速度档，给 MTPLX，不是 mlx-lm。官方谱系，README 没有无审查测试。这次没有加载，所以没有 tok/s |
| MTPLX 9B 6-bit | 约 8.1 GiB | 比现网 mxfp4 更大，不作为省内存的替换 |
| `qwen3.8-27b`（AEON 4-bit） | 14 GiB | 只做质量参照。转换说明偏向 32 GB 机器。24 GB 上不和 9B 同时加载，这次也没有单独加载 |
| `~/.cache/huggingface` 里的 `Qwen/Qwen2.5-1.5B-Instruct` | 约 2.9 GiB | 保护。不是生产模型，也没有证据证明它不是学习用的小文本模型。不删除 |

磁盘上没有名字像 Qwen 3B 的目录。`~/.mtplx/session-bank/blobs/3b` 只是哈希前缀。

## 没下载的候选

A5 核对过、这次没有拉取的包括：官方谱系的 deepsweet mxfp4、unsloth GGUF、`mlx-community/Qwen3-4B-Instruct-2507-4bit`（配置写 262144，但全注意力 KV 大约 144 KiB/token，不能按 262144 跑）、Gemma 4 E4B 4-bit（长上下文更省 KV，模型卡写了安全对齐，社区仓库许可证标签和官方 Apache 声明不一致）。细节在 `agents/A5-model-candidates.md`。

llama.cpp Metal 没有测。本机没有 `llama-cli` / GGUF。Qwen3.5 的 GGUF 还要求和 llama.cpp 的 rope section 长度匹配，不能假定随便一个 GGUF 能加载。

## 为什么不换

9B 在这台 M4 上 decode 中位数 21.4 tok/s，和「每个 token 读 5.3 GB 权重 / 约 120 GB/s」同一量级。4B 权重大约 2.4 GB，带宽上限粗算会更高，但这是算术，不是测量。要测就必须再占一块统一内存。32k 测试结束时 9B footprint 已经 8.2 GiB，jetsam 23，swap 事先就快满了。没有在这个状态下再加载 4B 或 27B。

换模型还会换掉已经验证过的 20000 字金额题和缓存行为。现网 9B 继续当基线。
