# A5 候选模型（2026-09-24）

适用机器：Apple M4、24GB 统一内存。用途：本地文本推理，MLX（`mlx-lm`）或 llama.cpp Metal。没有下载权重，没有 `git clone`，没有把任何检查点加载进 MLX，也没有调用生成接口。

结论先说：24GB 上的默认生产候选仍然是已经在磁盘上的 `TheCluster/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-MLX-mxfp4`（本机目录 `qwen3.5-9b-hauhau-aggressive-mxfp4`）。27B 只做质量参照。仓库名里的 “Uncensored” 不是证据。本机没有测量拒绝率，卡片上的数字也不能当成已经核实的拒绝率。

## 1. 怎么查的

文本权重名称只扫了两处：

- `/Users/rainhuang/Desktop/models` 第一层目录
- `~/.cache/huggingface/hub` 第一层仓库名

没有递归整个 home，没有删除任何文件。Kiln 的 `scripts/start-mtplx.sh` 写明模型在 `~/.mtplx/models`，所以只列了这一层目录，用来确认 4B/9B MTPLX 是否已经在本地。这不是第三次全盘搜索。

远程材料只取了 Hugging Face 的 `config.json`、模型卡 README 和 `api/models` 元数据（含 `blobs=true` 的文件字节）。官方 `meta-llama/Llama-3.1-8B-Instruct` 与 `google/gemma-3-4b-it` 的 config 返回 401，下面不把没打开的文件说成已读。

本机推理栈（只读 site-packages，未 import 权重）：

| 项 | 值 |
| --- | --- |
| 实际服务用的包 | `kiln/.venv` 里的 mlx-lm **0.31.3**（Python 3.12） |
| 另一份相同版本 | `/opt/homebrew/lib/python3.14/site-packages/mlx_lm`，同样是 0.31.3 |
| `start-mlx.sh` | 拒绝用 3.14 起服务（OpenMP 重复初始化） |
| 量化模式 | `mlx/nn/layers/quantized.py` 的 `_defaults_for_mode`：`affine`、`mxfp4`、`nvfp4`、`mxfp8` |
| 缺 `mode` 时 | `utils.py` 使用 `affine` |
| 与本文相关、且有对应 `mlx_lm/models/<name>.py` 的 `model_type` | `qwen2`、`qwen3`、`qwen3_5`、`gemma3`、`gemma4`、`llama`、`mistral3`、`ministral3` |

`qwen3_5.py` 的 `sanitize` 会丢掉 `vision_tower*` / `model.visual*`，并在语言模型 sanitize 里丢掉 `mtp.*`。所以现有 9B 可以走文本服务，但 MLX 这条路径不会用 MTP 头，也不会跑视觉塔。这是读源码，不是本次加载验证。

## 2. 本机已经有的文本模型

`du -sh` 与按文件字节相加一致（HF 缓存里 snapshot 是指向 blob 的符号链接；`du` 不重复计数）。

| 本地路径 | 仓库 | 修订 | 目录大小 | 角色 |
| --- | --- | --- | --- | --- |
| `/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4` | `TheCluster/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-MLX-mxfp4` | `a9e5f6d9aebfe8bae436bdd51da14dde5b1b30c9`（与 `kiln/MODEL.md`、`fetch-model.sh` 的 pin 相同） | 5,690,525,348 字节，`du` 5.3G | 默认候选，权重在此目录。Hub 缓存该仓库只有 4KB 的 `refs/main` |
| `/Users/rainhuang/Desktop/models/qwen3.8-27b` | `choppedgarlic/Qwen3.8-27B-AEON-ULTIMATE-UNCENSORED-4bit-MLX` | `875c8523f13294c90226d0a040f35e04366e83c7` | 15,153,257,115 字节，14.11 GiB | 质量参照，不是默认 |
| `~/.mtplx/models/Youssofal--Qwen3.5-4B-MTPLX-Optimized-Speed` | `Youssofal/Qwen3.5-4B-MTPLX-Optimized-Speed` | 见本地 `mtplx_runtime.json`（forge 记录上游 `Qwen/Qwen3.5-4B` sha `851bf6e806ef`） | 2,567,462,610 字节，2.39 GiB | 已在盘上的速度档。运行时是 MTPLX，不是 mlx-lm |
| `~/.mtplx/models/Youssofal--Qwen3.5-9B-MTPLX-Optimized-Speed` | `Youssofal/Qwen3.5-9B-MTPLX-Optimized-Speed` | 本地 `mtplx_runtime.json` 写 `mtplx_version` 0.3.8，`base_trunk` 为 `Qwen/Qwen3.5-9B` | 8,695,124,810 字节，8.10 GiB | 已在盘上。比 9B mxfp4 更重，仍不是默认 |
| `~/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct` | `Qwen/Qwen2.5-1.5B-Instruct` | `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` | `du` **2.9G** | **PROTECTED**。见第 6 节 |

Hub 上这两个已部署仓库今天仍在，且未 gated：TheCluster 下载数 6739，`safetensors.total` 9,409,813,744，blob 合计 5.69 GB；choppedgarlic 下载数 7371，`safetensors.total` 26,895,993,856，blob 合计 15.15 GB。本地目录字节和 Hub blob 合计只差几 KB，可以认为就是这两份权重，而不是另一套同名文件。

同目录下还有图像和视频树（Flux、Z-Image、Wan）。它们不是文本对话模型，本报告不把它们列入候选，也不建议删除。

在上述两个搜索根里，没有名字像 Qwen 3B 的目录。唯一的小文本模型是下面的 1.5B。

### 2.1 本机 9B mxfp4（默认）

来源：本地 `config.json`、`model.safetensors.index.json`、随仓库带的 README。摘录在 `raw/A5/local-qwen35-9b-hauhau.arch.json`。

- 架构：`Qwen3_5ForConditionalGeneration`，`model_type=qwen3_5`，文本 `qwen3_5_text`
- 量化：4 bit，`mode=mxfp4`，`group_size=32`。这个模式在当前 mlx 的合法模式表里
- 文本形状：hidden 4096，intermediate 12288，32 层，`full_attention_interval=4`，层类型计数 24 个 `linear_attention` + 8 个 `full_attention`
- 注意力：16 头 / 4 个 KV 头，`head_dim=256`。线性注意力 16 个 QK 头、32 个 V 头，头维 128
- 上下文：`max_position_embeddings=262144`。**没有** `sliding_window`。RoPE：`rope_theta=10000000`，`partial_rotary_factor=0.25`，`mrope_section=[11,11,10]`
- 词表 248320，`tie_word_embeddings=false`，`mtp_num_hidden_layers=1`
- 索引：1010 个张量，其中 `language_model` 677、`vision_tower` 333。`metadata.total_parameters=9409813744`，`total_size=5670289376`（张量字节，不是整个目录）
- tokenizer：`tokenizer_config.json` 的 `model_max_length=262144`，`eos_token=<|im_end|>`，`processor_class=Qwen3VLProcessor`
- 许可证：README 头 `license: apache-2.0`，`license_link` 指向 `Qwen/Qwen3.5-9B` 的 LICENSE。Hub `cardData.license` 也是 `apache-2.0`
- 卡片原话（不是本机结果）：写着 “0/465 refusals”，并声明没有改数据集、能力不损失；同时承认回答末尾仍可能加一句免责声明，并说那不是拒绝。标签含 `uncensored` / `decensored`。这些是作者声明
- 中间件：mlx-lm 服务本身不加内容分类器。Kiln 的 `MODEL.md` 也写了应用层不做 Chat 安全过滤。这不等于模型不会拒绝

判定：**保留，作为 24GB 默认。** 体积、架构和当前 mlx-lm 对得上，权重已经在默认 `MODEL_PATH`。262144 是配置上限，不是 24GB 上测过的可用长度。拒绝行为必须后测。

### 2.2 本机 27B 4-bit（只作参照）

摘录：`raw/A5/local-qwen38-27b-aeon.arch.json`。

- 同一套 `model_type=qwen3_5`。量化是 4 bit **affine**，group 64，不是 mxfp4
- 文本：hidden 5120，intermediate 17408，64 层，48 个线性层 + 16 个全注意力层，24 头 / 4 KV，`head_dim=256`
- `max_position_embeddings=262144`，无 sliding window，RoPE 与 9B 同型（theta 1e7，partial 0.25）
- 词表 248320，`tie_word_embeddings=false`，`language_model_only=false`，config 里有 image/video token id
- 权重索引却只有 `language_model`（1847 个张量），**没有** vision 或 mtp 张量。`total_parameters=26895993856`，`total_size=15132802048`
- 转换者 README：这是 `AEON-7/Qwen3.8-27B-AEON-ULTIMATE-UNCENSORED-BF16` 的 MLX 4-bit，转换本身不再做行为修改；**建议统一内存 32GB 或更多**；写明当前转换没有 `vision_config`，不支持图像。本地 config 实际没有 `vision_config` 键，和 README 一致
- 许可证字段：`apache-2.0`。Hub 今天仍是这个仓库，未 gated
- 上游官方形状：今天拉到的 `Qwen/Qwen3.8-27B` config 与这份文本形状一致（64 层、hidden 5120、262144）。官方卡把上下文写成原生 262144、可延伸到 1,000,000。AEON 仓库今天仍在（BF16 树页面可见）。AEON 的 GitHub README 自称 “willfully compliant”、用回答代替说教。这是作者描述，不是拒绝率

判定：**保留为质量参照，拒绝作为 24GB 默认。** 权重大约 14.1 GiB，再加 16 层全注意力的 KV 和系统占用，会顶到这台机器的舒适区之外。转换者自己写了 32GB。mlx-lm 能识别 `qwen3_5`，所以兼容风险不在架构名，而在内存。

### 2.3 本机 MTPLX 4B / 9B

摘录：`raw/A5/local-mtplx-qwen35-4b.arch.json`、`local-mtplx-qwen35-9b.arch.json`。

两者都是 `model_type=qwen3_5`，`max_position_embeddings=262144`，无 sliding window，RoPE 与上面的 9B 相同。4B：hidden 2560，intermediate 9216，32 层（24 线性 + 8 全注意力），16/4 头，`head_dim=256`，`tie_word_embeddings=true`，量化 **affine 4 bit、group 64**。9B 文本形状与 Hauhau 9B 相同，但量化是 **affine 6 bit、group 64**，并且带 `mtp.safetensors`。

README 许可证都是 `apache-2.0`。4B 卡写基座 `Qwen/Qwen3.5-4B`，并写 “2.47 GB on disk”。Hub blob 合计 2.57 GB，其中 `model.safetensors` 2.37 GB，与本机目录一致。9B Hub blob 合计 8.70 GB，本机 8.70 GB。两份 README 都没有写拒绝测试，也没有 “uncensored” 声明。它们是官方 Qwen3.5 的速度量化，不是 Hauhau 谱系。

4B 的 config 里有一条别人机器上的绝对路径（`/Users/youssof/.mtplx/...`），只出现在 `mtplx_mtp_payload_audit` 元数据里，不是本机缺文件。

判定：

- 4B：**保留为已在磁盘上的速度档**，给 MTPLX（`start-mtplx.sh` 默认 4B）。不要把它当成“已验证无拒绝”的生产替换。用 mlx-lm 加载会按源码丢掉 MTP，速度数字不再成立。
- 9B MTPLX：**保留为可选**，不作为默认。8.1 GiB 的 6-bit 加上视觉塔，比已经在服务路径上的 5.3G mxfp4 更挤，而且同样没有拒绝测量。

## 3. 远程候选

尺寸若无 “本机 du”，均来自今天的 Hub `blobs=true` 字节，或模型卡上的表格。上下文若无额外说明，来自该仓库 `config.json` 的 `max_position_embeddings`。下表的“全注意力 KV”是用 config 里的层数、KV 头、`head_dim`、bf16（2 字节）做的算术，**不是实测**：

`每 token 字节 = 全注意力层数 × KV头 × head_dim × 2 × 2`

混合模型里线性层的状态不随序列变长，没有算进去。24GB 机器还要留系统、权重和激活。

### 3.1 要保留的

| 仓库 | 量化 | 大小 | 配置上下文 | 架构要点 | 许可证 | 已在本地？ | mlx-lm 0.31.3 风险 | 判定 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `TheCluster/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-MLX-mxfp4` | mxfp4，group 32 | 本机 5.30 GiB；Hub 5.69 GB | 262144，无滑动窗口 | `qwen3_5`，32 层，8 层全注意力，KV 头 4，head 256。约 32 KiB/token | apache-2.0（卡头 + Hub） | 是 | 低。`qwen3_5` 已注册，mxfp4 在模式表内。视觉塔会被丢掉，MTP 会被丢掉 | **默认保留** |
| `deepsweet/Qwen3.5-9B-MLX-MXFP4` | 卡上的命令是 `mlx_lm.convert --q-mode mxfp4 --q-group-size 32`，mlx-lm 0.30.7 | `model.safetensors` 4.76 GB；目录 4.78 GB。API `safetensors.total` 8,953,803,264 | 未再单独打开它的 config；基座是 `Qwen/Qwen3.5-9B`，官方 config 为 262144 | 官方 9B 文本形状见下。页面小部件曾把尺寸标成 “2B”，与 API 参数计数和转换命令矛盾，以 API 和命令为准 | apache-2.0 | 否 | 低到中。同架构、同量化模式，但是另一份量化，未加载 | **保留为以后的官方谱系对照**，不是现在的默认。用来和 Hauhau 比拒绝行为，而不是替换 |
| `unsloth/Qwen3.5-9B-GGUF` | 仓库里有多档 GGUF，含 Q4/Q3/BF16 文件名 | 本次没有逐个文件取字节 | 官方 config 262144 | llama.cpp / Metal 路径，不是 mlx-lm | apache-2.0，未 gated | 否 | 不走 mlx-lm。GGUF 能否加载取决于 llama.cpp 版本，见 3.3 | **保留为 Metal/GGUF 对照** |
| `HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive` | 卡上的表：BF16 17 GB，Q8_0 8.9 GB，Q6_K 6.9 GB，Q4_K_M 5.3 GB，另有 mmproj 880 MB | 同上，是卡片表格，不是本次 blob 计数 | 卡片沿用 Qwen3.5 的 262K，并提到可 YaRN 到约 1M | GGUF。与本机 MLX 同一上游声明 | apache-2.0，Hub 未 gated，下载数 719464 | 否（本地是 TheCluster 的 MLX，不是这份 GGUF） | 不走当前 mlx-lm 服务 | **保留为同一谱系的 GGUF 形态**。拒绝声明与 MLX 卡是同一段作者文字 |
| `Youssofal/Qwen3.5-4B-MTPLX-Optimized-Speed` | affine 4 bit，group 64，另有 MTP | 本机 2.39 GiB | 262144，无滑动窗口 | `qwen3_5`，hidden 2560，32 层，8 层全注意力。KV 估算同样约 32 KiB/token（KV 头和 head_dim 与 9B 相同） | apache-2.0 | 是 | 给 MTPLX，不是给 mlx-lm 的 MTP 路径 | **保留为速度档** |
| `Qwen/Qwen3.5-4B` | 官方未量化 | Hub `safetensors.total` 4,659,865,088 | 今天拉到的 config：262144，无滑动窗口，24 线性 + 8 全注意力，hidden 2560，`tie_word_embeddings=true` | 与本机 MTPLX 4B 文本形状一致 | apache-2.0，未 gated | 否（只有 MTPLX 量化） | BF16 不必直接拿来当 24GB 默认。量化体已在 MTPLX 目录 | 基座存在。生产用已经落地的 4B 量化，不要再下 BF16 |
| `Qwen/Qwen3.5-9B` | 官方未量化，4 个 safetensors 分片 | Hub 参数计数 9,653,104,368 | config：262144，无滑动窗口，hidden 4096，32 层，8 层全注意力，词表 248320 | 官方 post-trained，多模态 | apache-2.0，未 gated，下载数约 9.8M | 否 | BF16 大约十几 GB 量级，不适合再叠加长 KV 当默认。mlx-lm 认识这个 `model_type` | 基座存在。要官方行为用 deepsweet 那份 mxfp4，或 unsloth GGUF，而不是下 BF16 |
| `mlx-community/Qwen3-8B-4bit` 与 `Qwen/Qwen3-8B-GGUF` | MLX 4 bit group 64，config 无 `mode`（加载时按 affine）。GGUF 含 `Qwen3-8B-Q4_K_M.gguf` 5.03 GB | MLX 目录 4.62 GB，权重 4.61 GB | **40960**，`sliding_window=null`，`rope_theta=1000000` | `model_type=qwen3`，`Qwen3ForCausalLM`，hidden 4096，36 层全是普通注意力，32 头 / 8 KV，head 128。KV 估算约 144 KiB/token，比 Qwen3.5-9B 重得多 | 两边都是 apache-2.0 | 否 | 低。`qwen3.py` 在，缺 mode 会走 affine。GGUF 走 llama.cpp | **保留为回退，不作为默认。** 更旧、上下文只有 40,960，而且是对齐过的 instruct，没有“无拒绝”声明 |
| `mlx-community/Qwen3-4B-4bit` 与 `Qwen/Qwen3-4B-GGUF` | 同上，4 bit。GGUF `Q4_K_M` 2.50 GB | MLX 2.28 GB，权重 2.26 GB | **40960** | `qwen3`，hidden 2560，36 层，32/8，head 128，`tie_word_embeddings=true`。KV 估算仍约 144 KiB/token | apache-2.0 | 否 | 低 | **保留为小回退。** 上下文短，KV 并不比 8B 便宜 |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | 4 bit group 64，无 mode | 2.28 GB | **262144**，`rope_theta=5000000`，其余形状与原版 Qwen3-4B 相同（36 层，32/8，head 128） | 纯文本 `Qwen3ForCausalLM` | apache-2.0 | 否 | 架构名风险低。上下文风险高：262144 × 约 144 KiB 的 KV 远超 24GB | **有条件保留。** 只有在把运行时上下文砍到远低于 262144 时才放得进 24GB。配置里的 262144 不是可运行长度 |
| `mlx-community/gemma-4-e4b-it-4bit` | affine 4 bit，group 64（这份 MLX config 写了 `mode`） | 目录 5.18 GB，`model.safetensors` 5.15 GB | **131072**，`sliding_window=512` | `model_type=gemma4`。42 层 = 35 滑动 + 7 全注意力，hidden 2560，8 头 / 2 KV，head 256，词表 262144，`tie_word_embeddings=true`。全注意力 KV 估算约 14 KiB/token，滑动层有窗口 | 官方 `google/gemma-4-E4B-it` 的 Hub 与 README 头都是 **apache-2.0**，并链到 `https://ai.google.dev/gemma/docs/gemma_4_license`。该 URL 本次没有打开。社区 4bit 仓库的 Hub `cardData.license` 却是 **`gemma`**，和官方卡不一致 | 否 | 中低。`gemma4.py` 会丢掉 vision/audio tower；`rope_utils.py` 有 `proportional`。未加载，不能保证社区包每个张量名都能过 sanitize | **保留为非 Qwen 对照，不作为默认。** 长上下文比 Qwen3.5 省 KV。模型卡写明做过安全对齐，见下 |
| `mistralai/Ministral-3-8B-Instruct-2512-GGUF` | 官方 GGUF：`Q4_K_M` 5.20 GB，Q5_K_M 6.06 GB，Q8_0 9.03 GB，BF16 16.99 GB，另有 mmproj 0.86 GB | 见左 | 文本 config：`max_position_embeddings=262144`，`sliding_window=null` | 顶层 `mistral3`，文本 `ministral3`。34 层，hidden 4096，32 头 / 8 KV，head 128，intermediate 14336。RoPE 是 YaRN，`factor=16`，`original_max_position_embeddings=16384`，`rope_theta=1e6`。无滑动窗口时 KV 估算约 136 KiB/token | apache-2.0。卡上还有一句不得侵犯第三方权利，这不是推理中间件 | 否 | GGUF 走 llama.cpp，不依赖 mlx-lm。全长 256K 在 24GB 上不成立 | **保留为 GGUF 对照。** 运行时把上下文降到几十 K 以内才适合 24GB |
| `mlx-community/Ministral-3-8B-Instruct-2512-4bit` | 4 bit MLX，目录 5.63 GB | 5.63 GB | 应继承上面的 262144；本次没有再打开这一份的 config | 卡写明用 **mlx-vlm 0.3.9** 从官方 FP8 转出，不是 mlx-lm 0.31.3 的 convert 日志 | apache-2.0 | 否 | 中。mlx-lm 有 `mistral3.py`，且会在 `text_config.model_type==ministral3` 时转到 `ministral3.py`。官方 FP8 config 的 `quant_method=fp8` **不在** mlx-lm 处理的 quant_method 列表里，不能把官方 FP8 仓库直接丢给 mlx-lm。4bit 社区包还可能带 mistral-common 分词器 | **可以留作 MLX 试验，不作为默认。** 优先用上面的官方 GGUF |

Gemma 4 官方卡（`google/gemma-4-E4B-it` README，今天拉下）还写了这些，和“能不能无中间件运行”有关：

- 安全测试“没有加 safety filters”，目的是看模型本身。
- 相对 Gemma 3，作者声称安全类别更好，“unjustified refusals”更低。没有给出本报告可以引用的拒绝率分数。
- 开发者被鼓励按自己的产品政策再加内容安全措施。那是建议，不是权重运行的前置条件。
- Google 模型卡表格：E4B 为 4.5B effective（算上 embedding 约 8B），滑动窗口 512，上下文 128K。Hub 参数计数 7,996,156,490，和“含 embedding 约 8B”同一量级。
- 因此：Gemma 4 可以在没有额外审核中间件的情况下加载，但权重本身是安全对齐过的。要不要用，取决于后测，不取决于仓库名。

### 3.2 拒绝作为默认

| 仓库 | 为什么不作为 24GB 默认 |
| --- | --- |
| `choppedgarlic/Qwen3.8-27B-AEON-ULTIMATE-UNCENSORED-4bit-MLX` 与官方 `Qwen/Qwen3.8-27B` | 质量参照。4-bit 已约 14.1 GiB，卡建议 32GB。官方 BF16 更不是 24GB 的默认。名字里的 uncensored 仍未在本机测量 |
| `mlx-community/Meta-Llama-3.1-8B-Instruct-4bit` 与 `bartowski/Meta-Llama-3.1-8B-Instruct-GGUF`、`lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF` | MLX 与 GGUF **都存在**，所以不是“没有格式”。MLX 4.53 GB，config：`model_type=llama`，hidden 4096，32 层，32/8 头，`max_position_embeddings=131072`，`rope_theta=500000`，`rope_scaling.type=llama3`（`original_max_position_embeddings=8192`，factor 8）。`llama.py` 加 `rope_utils.py` 的 `llama3` 分支在源码里存在。拒绝原因是许可证和定位：Hub `license` 为 **`llama3.1`**，不是 Apache-2.0；官方 `meta-llama/Llama-3.1-8B-Instruct` 本次 401（gated）。Instruct 是安全对齐模型。公开语言列表是 8 种，不以中文为主要训练语言。128K 的全注意力 KV（约 128 KiB/token）在 24GB 上也不能拉满 |
| `mlx-community/gemma-3-4b-it-4bit` | 许可证标签是 **`gemma`**（Gemma 3 条款，不是 Gemma 4 的 Apache 声明）。这份 MLX config **没有** `max_position_embeddings`，只有 `sliding_window=1024` 和线性 RoPE factor 8。`gemma3_text.py` 在缺字段时把 `max_position_embeddings` **默认成 32768**。官方 Gemma 3 仓库本次 401，不能把宣传材料里的 128K 写成这个文件里的值。有 Gemma 4 E4B 就不必用它当默认 |
| Mistral Small 24B 一级（Small 3 / 3.1 / 3.2） | 不在 4B–9B 档。4-bit 会落在和 27B 相同的内存区。本次没有把它的 config 当作候选打开 |
| Qwen3.5 MoE（如 35B-A3B、122B-A10B） | 不在 4B–9B 密集档。公开内存说明把 4-bit 放在二十 GB 上下或更高。24GB 默认不选。本次没有把它们的 config 收进 `raw/A5` |

`Qwen/Qwen3.5-9B-GGUF` 这个官方 ID 本次返回 401，不把它算作存在的官方 GGUF。可用的 GGUF 是 `unsloth/Qwen3.5-9B-GGUF` 和 HauhauCS 那份。

### 3.3 llama.cpp / Metal 的一个已公开坑

2026-09-12 的 LM Studio 问题单记录：Ollama 的 Qwen3.5 4B GGUF 在一份 llama.cpp Metal 运行时里加载失败，原因是 `qwen35.rope.dimension_sections` 期望长度 4、文件里是 3。同一时期 Hugging Face 的说明（2026-09-22）把 Qwen3.5 列为 Apple Silicon 上可以跑的 llama.cpp quant 架构。两件事同时成立：架构有人在 Metal 上跑通，但 **GGUF 生产者和 llama.cpp 版本必须匹配**。本报告没有在这台机器上启动 llama.cpp。

## 4. 24GB 上上下文能不能开到配置上限

只按第 3 节的算术，不报实测 tok/s：

| 模型 | 全注意力 KV | 32K 仅 KV | 配置上限仅 KV | 含义 |
| --- | --- | --- | --- | --- |
| Qwen3.5-9B / 4B | 约 32 KiB/token | 约 1.0 GiB | 262144 → 约 8 GiB | 权重 2–6 GiB 时，32K–64K 量级比拉满 256K 更像 24GB 的工作区。没有滑动窗口，KV 线性涨 |
| Qwen3.8-27B | 约 64 KiB/token | 约 2 GiB | 约 16 GiB | 再加上 14 GiB 权重，不适合默认拉长上下文 |
| Qwen3-8B / Qwen3-4B | 约 144 KiB/token | 约 4.5 GiB | 40960 → 约 5.6 GiB；2507 的 262144 会到数十 GiB | 权重小不等于上下文便宜 |
| Gemma 4 E4B | 全注意力约 14 KiB/token，另有 512 的滑动窗口 | 明显小于 Qwen3.5 | 131072 的全注意力部分约 1.8 GiB | 这是它相对 Qwen3.5 的实际优点，仍需后测质量 |
| Ministral 3 8B | 约 136 KiB/token，无滑动窗口 | 约 4.2 GiB | 262144 不可行 | 用 GGUF 时必须自己设上下文 |

`kiln/docs/inference-mlx.md` 记录过这台 M4 的 Metal 建议工作集约 17.76 GiB。那是当时的笔记，本次没有重新调用 `mx.device_info()`。

## 5. 拒绝行为：现在不能写数字

本机没有跑提示集。下面任何分数都 **不是** 本报告的测量：

- Hauhau 卡片写 “0/465 refusals”，并承认可能在全文之后附加免责声明。
- 第三方页面（abliterlitics 等）也给过自己的套件分数。那些不是这次实验。
- AEON 作者把 27B 描述成会直接回答。choppedgarlic 的 MLX 卡没有再报一个拒绝分数，只说转换时没有再改行为。
- Gemma 4 卡声称安全更好、无故拒绝更低，测试时没有外挂过滤器，同样没有可被本报告当作本机结果的分数。
- 官方 Qwen3、Ministral 3、Llama 3.1 Instruct 都是 post-trained instruct。没有在已读卡片里看到“运行必须先挂一个审核模型”，但它们会不会拒绝，只能后测。

以后若要测，用固定的中英提示集，至少分开三类：明显不该答的请求、普通成人写作、完全良性的问答。每条只记四种结果：直接拒绝、先答完再加免责声明、答非所问、空回复。对照至少包括官方谱系的 Qwen3.5-9B（deepsweet mxfp4 或 unsloth GGUF）和本机 Hauhau。不要把仓库名或卡片上的 0/465 填进结果表。同时确认服务进程没有另外挂分类器；当前 mlx-lm 路径和 Kiln 文档都是没有应用层过滤。

## 6. PROTECTED，不是删除对象

`Qwen/Qwen2.5-1.5B-Instruct`，修订 `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`，在 Hugging Face 缓存里，`du` 2.9G。完整 config 已复制到 `raw/A5/protected-qwen25-1.5b.config.json`。

- `Qwen2ForCausalLM`，`model_type=qwen2`（mlx-lm 有 `qwen2.py`）
- hidden 1536，28 层，12 头 / 2 KV，`max_position_embeddings=32768`，`sliding_window=32768`，但 `use_sliding_window=false`
- `rope_theta=1000000`，词表 151936，`tie_word_embeddings=true`，`torch_dtype=bfloat16`
- 本机 snapshot 没有 LICENSE 文件。本次没有再打开上游 README，所以不把许可证写成已经核对
- 它低于 4B 档，也不是当前服务模型。列出它只是为了防止后续清理把它当成可删的小模型

两个搜索根里没有其他名字像 Qwen 3B 或更小因果语言模型的目录。

## 7. 建议（仍然不下载）

1. 默认继续用本机 Hauhau 9B mxfp4，mlx-lm 0.31.3，Python 3.12。不要为了卡片上的拒绝数字把它换成另一个没测过的 “uncensored” 仓库。
2. 27B 留在磁盘上当质量参照。不要把它设成 24GB 的常驻默认，也不要为了它去下官方 BF16。
3. 需要更快、且可以接受官方对齐时，用已经在 `~/.mtplx` 的 4B，走 MTPLX，不要假装 mlx-lm 会用它的 MTP。
4. 若下一轮要做行为对照，优先排队而不是现在下载：`deepsweet/Qwen3.5-9B-MLX-MXFP4`（官方谱系、同一种 mxfp4）或 `unsloth/Qwen3.5-9B-GGUF`。换家族则看 Gemma 4 E4B 4-bit（更省长上下文 KV，但是安全对齐；先核对社区仓库许可证标签为何是 `gemma`）。
5. Qwen3-8B/4B 的 MLX 与官方 GGUF 都还在，只能当短上下文回退。Llama 3.1 8B 格式齐全，但许可证不是 Apache，不作为默认。

## 8. 原始摘录

`/Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/raw/A5/`

- `local-*.arch.json`：本机四份文本 config 的架构字段（去掉了逐层 `layer_types` 列表，保留计数）
- `protected-qwen25-1.5b.config.json`：1.5B 的完整 config
- `remote/`：今天从 Hub 拉下的 config.json（不是权重）
- `slim-*.arch.json`：上述远程 config 的同一套字段摘录
- `mlx-lm-0.31.3-support.json`：版本、量化模式、相关 `model_type` 模块名

## 9. 来源

本机：上述 config、index、README、tokenizer_config；`kiln/scripts/start-mlx.sh`、`fetch-model.sh`、`start-mtplx.sh`；`kiln/MODEL.md`；mlx-lm 0.31.3 的 `utils.py`、`models/qwen3_5.py`、`models/gemma4.py`、`models/mistral3.py`、`models/ministral3.py`、`models/gemma3_text.py`、`models/rope_utils.py`；`mlx/nn/layers/quantized.py`。

Hub（2026-09-24 打开过 config 或 API）：

- https://huggingface.co/Qwen/Qwen3.5-9B
- https://huggingface.co/Qwen/Qwen3.5-4B
- https://huggingface.co/Qwen/Qwen3.8-27B
- https://huggingface.co/Qwen/Qwen3-8B
- https://huggingface.co/Qwen/Qwen3-4B
- https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507
- https://huggingface.co/Qwen/Qwen3-8B-GGUF
- https://huggingface.co/Qwen/Qwen3-4B-GGUF
- https://huggingface.co/TheCluster/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-MLX-mxfp4
- https://huggingface.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive
- https://huggingface.co/deepsweet/Qwen3.5-9B-MLX-MXFP4
- https://huggingface.co/unsloth/Qwen3.5-9B-GGUF
- https://huggingface.co/choppedgarlic/Qwen3.8-27B-AEON-ULTIMATE-UNCENSORED-4bit-MLX
- https://huggingface.co/Youssofal/Qwen3.5-4B-MTPLX-Optimized-Speed
- https://huggingface.co/Youssofal/Qwen3.5-9B-MTPLX-Optimized-Speed
- https://huggingface.co/google/gemma-4-E4B-it
- https://huggingface.co/mlx-community/gemma-4-e4b-it-4bit
- https://huggingface.co/mlx-community/gemma-3-4b-it-4bit
- https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512
- https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF
- https://huggingface.co/mlx-community/Ministral-3-8B-Instruct-2512-4bit
- https://huggingface.co/mlx-community/Qwen3-8B-4bit
- https://huggingface.co/mlx-community/Qwen3-4B-4bit
- https://huggingface.co/mlx-community/Qwen3-4B-Instruct-2507-4bit
- https://huggingface.co/mlx-community/Meta-Llama-3.1-8B-Instruct-4bit
- https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF

AEON 上游说明：https://github.com/AEON-7/Qwen3.8-27B-AEON-ULTIMATE-UNCENSORED  
GGUF 版本坑的公开记录：https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/2398
