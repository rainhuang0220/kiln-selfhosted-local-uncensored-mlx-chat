# A7：当前本地 Qwen MLX 的 KV cache

只读调研。没有加载权重，没有对正在服务的模型做生成，没有改 kiln 源码，也没有部署任何 KV 压缩原型。下面的字节数全部是由 `config.json` 和 mlx-lm 源码推出的估算，不是 `nbytes` 或峰值内存的实测。

当前进程配置的模型是 9B：`/Users/rainhuang/Library/Application Support/kiln/start-mlx.sh` 指向 `/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4`。27B 权重在 `/Users/rainhuang/Desktop/models/qwen3.8-27b`，没有挂到这个启动脚本上。两边都是 `model_type: qwen3_5`。

## 结论

随上下文变长的只有全注意力 KV。9B 是 32 层里的 8 层，27B 是 64 层里的 16 层。其余层是 Gated DeltaNet，状态大小与 token 数无关。

线上 `mlx_lm.server` 没有 KV 量化，也没有旋转窗口。已有的 `--prompt-cache-size` 是多份前缀复用，不是压缩。权重的 mxfp4 / affine 4-bit 也不作用于 KV。

先做的实验应是：离线、单独进程，用现成 CLI `--kv-bits` 只压那 8 层全注意力，并和未压缩缓存比质量。不要先移植 SnapKV / PyramidKV / KVPress。它们挂在 Hugging Face transformers 的注意力上，不能原样落到这份 MLX 上。

## 1. 配置里和 cache 有关的数

两份 `config.json` 都没有 `sliding_window`。`max_position_embeddings` 都是 262144。`text_config.dtype` 都是 `bfloat16`。`use_cache` 都是 true。

全注意力层数由 `full_attention_interval: 4` 决定，和 `layer_types` 的计数一致。mlx-lm 不读 `layer_types`，它用 `(layer_idx + 1) % 4 != 0` 判定线性层（`qwen3_5.py` 第 212 行）。

| | 9B（当前） | 27B（在盘上，未作为默认服务） |
|---|---|---|
| 层数 | 32 | 64 |
| 全注意力 / 线性 | 8 / 24 | 16 / 48 |
| Q 头 / KV 头 / head_dim | 16 / 4 / 256 | 24 / 4 / 256 |
| hidden | 4096 | 5120 |
| 线性 K 头 × 维 | 16 × 128 | 16 × 128 |
| 线性 V 头 × 维 | 32 × 128 | 48 × 128 |
| conv kernel | 4 | 4 |
| 权重量化 | mxfp4，group 32，4 bit | affine，group 64，4 bit |
| 权重分片字节 | 5 670 414 861 | 15 133 043 513 |

`head_dim` 必须用配置值 256。27B 的 `5120 / 24` 不是 256。

RoPE：两边都是 `rope_theta = 1e7`，`partial_rotary_factor = 0.25`，并带有 `mrope_section = [11, 11, 10]`、`mrope_interleaved = true`。类型是 `default`，不是 yarn。9B 模型卡写「YaRN 可扩到 1M」，配置里没有 YaRN 的 factor，不能当成已启用。

`mtp_num_hidden_layers` 为 1，但两份 `model.safetensors.index.json` 里都没有 `mtp` 张量。9B 有 `vision_config` 和 333 个视觉张量；27B 没有 `vision_config`，视觉张量为 0（尽管 `language_model_only` 写成 false）。

## 2. 安装的 mlx-lm 里有哪些 cache，Qwen3.5 实际用哪一个

`which mlx_lm` 是 `/opt/homebrew/bin/mlx_lm`，解释器 Python 3.14，包在 `/opt/homebrew/lib/python3.14/site-packages/mlx_lm`，版本 **0.31.3**（mlx 0.32.1）。Kiln 实际启动用的是 `.venv` 的 Python 3.12，版本同样是 mlx-lm 0.31.3。`models/cache.py`、`models/qwen3_5.py`、`generate.py` 与 Homebrew 那份 `diff -q` 无差异。服务端不要用 3.14 那条 `mlx_lm`（启动脚本会因 OpenMP 拒绝 3.14）。

`model_type == qwen3_5` 时加载 `mlx_lm.models.qwen3_5.Model`（`utils.py` 第 185–193 行）。这个类的 `make_cache` 转给文本模型：

```304:305:/opt/homebrew/lib/python3.14/site-packages/mlx_lm/models/qwen3_5.py
    def make_cache(self):
        return [ArraysCache(size=2) if l.is_linear else KVCache() for l in self.layers]
```

外层 `Model.make_cache` 在第 522–523 行，只是再委托一次。因此架构类实际构造的是：

- 线性层：`ArraysCache(size=2)`。槽 0 是 conv 状态，槽 1 是 Gated DeltaNet 循环状态。
- 全注意力层：普通 `KVCache`，不是 `RotatingKVCache`，也不是 `QuantizedKVCache`。

全注意力实现是 `Qwen3NextAttention`（`qwen3_next.py` 第 145–148 行）：对 K/V 做 RoPE 后 `cache.update_and_fetch(keys, values)`。没有滑动窗口。

RoPE 模块按已缩小的维度构造：`int(head_dim * 0.25) = 64`（`qwen3_next.py` 第 113–118 行）。`rope_parameters.type` 经 `qwen3_5.py` 第 72–83 行变成 `default` 后，`rope_utils.py` 第 249–251 行走 `nn.RoPE(64, base=1e7)`。配置里的 MRoPE 分段不会被用到。即便类型被写成 `mrope`，第 301–306 行也只是断言三段然后仍返回普通 `nn.RoPE`。

`Model.__call__` 只跑语言模型（第 374–381 行）。`sanitize` 丢掉 `vision_tower` / `model.visual`（第 387–388 行）和 `mtp.*`（第 313 行）。所以即使用 9B 多模态权重，这条推理类也不建视觉 cache。

### 各类 cache 在做什么

都在 `/opt/homebrew/lib/python3.14/site-packages/mlx_lm/models/cache.py`。

| 类 | 行 | 作用 | Qwen3.5 |
|---|---|---|---|
| `make_prompt_cache` | 15–40 | 有 `make_cache` 就用模型自己的；只有没有时，`max_kv_size` 才会建成 `RotatingKVCache(..., keep=4)` | 有 `make_cache`，因此单请求路径的 `--max-kv-size` 被忽略 |
| `KVCache` | 325–407 | 按 256 token 一步扩容的稠密 K/V；可 trim；`to_quantized` 整段换成量化 cache | 全注意力层的构造类型 |
| `QuantizedKVCache` | 232–322 | `mx.quantize` 的仿射打包：uint32 码 + 每组 scale 和 bias，dtype 跟原 K/V 走 | 只有 CLI 设了 `--kv-bits` 才会换上 |
| `RotatingKVCache` | 410–591 | 超过 `max_size` 就丢掉旧 token，可保留开头 `keep` 个。`to_quantized` 直接 `NotImplementedError`（第 551–552 行） | 架构不用。只有 `BatchGenerator._make_new_cache` 在传入 `max_kv_size` 时会把 `KVCache` 换成它，且 `keep` 默认 0 |
| `ArraysCache` | 594–728 | 固定个数的数组。没有重写 `is_trimmable`，基类第 146 行是 False。没有 `to_quantized` | 每个线性层一个，长度 2 |
| `ChunkedKVCache` | 731 | 只留最近一个 chunk | 不用 |
| `ConcatenateKVCache` | 178 | 朴素拼接 | 不用 |
| `CacheList` | 814 | 一层里放多种 cache | 不用。这里线性层和全注意力层是列表里不同元素 |
| `BatchKVCache` | 912–1118 | 左填充的批量 KV。`merge` 在第 1089 行；`extract`（第 1080 行）再变回 `KVCache` | 服务端把多条请求合成一批时用 |
| `BatchRotatingKVCache` | 1133 | 批量旋转窗口。量化同样未实现（第 1327–1328 行） | 服务端没开 |
| `LRUPromptCache` | 1623–1754 | 按 token 前缀保存多份 cache。默认 10 条、字节上限 `1<<63`（第 1659 行） | 服务端在用，但是份数上限，不是压缩 |

`save_prompt_cache` / `load_prompt_cache` 在第 43–86 行，写成 safetensors。这是 CLI 的 `--prompt-cache-file`，HTTP 服务没有这个参数。

量化入口在 `generate.py` 第 299–304 行：`kv_bits is None` 就返回；只处理有 `to_quantized` 且 `offset >= quantized_kv_start` 的层。`ArraysCache` 被跳过。默认 `quantized_kv_start` 是 5000（第 56 行），`--kv-group-size` 默认 64（第 197–201 行）。一旦越过阈值，`KVCache.to_quantized` 会把已经写下的整段 K/V 都量化，不是只量化阈值之后的 token。

### 服务进程实际走的路径

`server.py` 没有 `--kv-bits`、`--kv-group-size`、`--quantized-kv-start`、`--max-kv-size`。正在用的启动参数是 `--prompt-cache-size 4 --prompt-cache-bytes 4G`。`utils.py` 第 60–69 行把 `4G` 解析成 `4 * 1e9 = 4_000_000_000` 字节，不是 4 GiB。

无 draft、且请求没带 seed 时，模型被当成可批处理（`server.py` 第 371–374 行：`make_prompt_cache` 的每一项都有 `merge`；`KVCache` 和 `ArraysCache` 都有）。`BatchGenerator` 在第 821–827 行创建，不传 `max_kv_size`。新 cache 仍来自 `make_cache()`（`generate.py` 第 1657–1659 行）。合成一批时 `_merge_caches`（第 870–878 行）把全注意力层变成 `BatchKVCache`，线性层仍是 `ArraysCache`。写回 LRU 时 `extract` 又变回 `KVCache`。

带 seed 的单请求走 `stream_generate`（`server.py` 第 976 行），同样不传 `kv_bits`。`generate.py` 第 838 行的 `_make_cache` 在这棵 0.31.3 里没有调用点，不要把它当成线上路径。

因此当前 9B 服务的 cache 是：24 个不可裁剪的 `ArraysCache`，加上 8 个未量化的全注意力 KV（批内是 `BatchKVCache`，放进 LRU 时是 `KVCache`）。没有旋转，没有 int8/int4 KV。

两个直接后果：

1. `can_trim_prompt_cache` 要求每一层都可裁（`cache.py` 第 88–92 行）。线性层不行，所以更长前缀不能裁成公共前缀（第 1683–1688 行）。能复用的是「已存的更短前缀」。投机解码会直接报错（`generate.py` 第 529–533 行）。不要给这台服务加 `--draft-model`。
2. `generate.py` 第 1980 行只在 `prompt_cache[0]` 是 `QuantizedKVCache` 时核对 bit 数。Qwen3.5 的第 0 层是线性层，这条检查看不到全注意力层的量化参数。

循环状态的形状在 `gated_delta.py` 第 48 行和第 239、276–279 行：`[B, Hv, Dv, Dk]`，初始 `float32`。conv 状态在 `qwen3_5.py` 第 148–166 行，只留 `kernel_size - 1` 帧，dtype 跟激活走。

## 3. 三个外部项目的 README，以及为什么不能直接套上 MLX

只读了 README，没有读论文。摘录在 `raw/A7/03-readme-notes.md`。

**NVIDIA KVPress**（https://github.com/NVIDIA/kvpress ，blob `bace06dab057a7610b3c7fb5a8185bee2478dee9`）。训练无关的 press，在 prefill 时按 `compression_ratio` 压缩 KV。做法是给每一层注意力注册 `forward_hook`，或走 transformers pipeline 名 `kv-press-text-generation`。README 里 SnapKV 的一行定义是「最近若干 query 的平均注意力权重」；PyramidKV 是「金字塔预算：低层多、高层少」。量化走的是 transformers 的 `QuantizedCache`（quanto），默认 cache 是 `DynamicCache`。FAQ 写明测过 Llama、Mistral、Phi-3、Qwen2、Qwen3、Gemma3，没有 Qwen3.5，也没有线性注意力。示例是 CUDA。

**SnapKV**（https://github.com/FasterDecoding/SnapKV ，blob `1e505781926098398c104039aac9708a50385cb8`）。README 自己只说这是开箱即用的 KV 压缩，计分公式不在 README 里，而在 `snapkv_utils.py`。接法是 monkeypatch：`replace_mistral()`，以及 Llama / Mistral / Mixtral 的 hijack。钉的是 `transformers==4.37` 一带和 `flash-attn==2.4.0`。

**PyramidKV**（https://github.com/Zefan-Cai/PyramidKV ，blob `b6544df475a66e24ff54682bd5ccb21b36d05724`）。这个 README 的标题已经改成 KVCache-Factory（2024-11-28 改名）。PyramidKV 仍是其中一行：「按层的金字塔 cache 预算」。`--max_capacity_prompts` 是每层预算，PyramidKV 再把总预算分到各层。运行器是 `run_longbench.py --method pyramidkv`，依赖 `transformers==4.44.2`、torch、可选 flash-attn。正文写 Llama 和 Mistral 的注意力路径。这不是 MLX 包。

不能原样落到本机的原因：

1. 三者都改 Hugging Face 的 `past_key_values` / `DynamicCache`，或在 PyTorch 注意力的 forward 上打补丁。mlx-lm 的全注意力把 K、V 放进 `KVCache.update_and_fetch`，注意力在 MLX 的 scaled dot-product 里，没有 transformers hook，也没有 flash-attn。
2. 它们假定每一层都有随 token 增长的 K/V。这份模型四分之三的层是固定大小的 conv + float32 循环状态，没有可按 token 丢掉的 KV。把 press 套到「所有层」在类型上就不成立。
3. 就算只改 8 层全注意力，也要重写选 token、改 cache 长度、以及和 `BatchKVCache` 的 padding / `extract` 的配合。`QuantizedKVCache` 是打包后的 uint32 加 scale，不是可以按下标切片的稠密张量。
4. KVPress 的重旋转类方法假设标准 RoPE。这里只旋转 head 的 64 维，配置里的 MRoPE 分段在 0.31.3 里没有生效。
5. 低层多预算、高层少预算，是针对一叠 softmax 层。这里的低层大多是 DeltaNet，8 个全注意力层均匀隔 4 层，不是一座 softmax 金字塔。
6. 服务进程没有插入 press 的参数。装上这些仓库也不会改变 `:8081`。

## 4. 每 token 的 KV 字节估算

不是实测。`KVCache.step = 256`，`nbytes` 含尚未写满的 padding，所以实测会高于或短暂高于下面的「已占用逻辑字节」。量化 cache 同样按 256 步预分配。

只计算会随 token 增长的全注意力 K 和 V。线性层另算，而且不乘 token 数。

```
每 token 元素数 = 全注意力层数 × 2 × num_key_value_heads × head_dim
9B  = 8  × 2 × 4 × 256 = 16384
27B = 16 × 2 × 4 × 256 = 32768

bf16 或 fp16 载荷 = 元素数 × 2
int8 裸载荷     = 元素数 × 1
int4 裸载荷     = 元素数 × 0.5
```

配置写的是 bfloat16。没有量过激活实际 dtype。bf16 和 fp16 都是 2 字节，所以「fp16 KV」和「bf16 KV」在这张表里是同一个数。今天线上就是这个未压缩载荷（外加 256 对齐），不是 int4。

`QuantizedKVCache` 不是 mxfp4。它是仿射量化：打包位加上每 `group_size` 一个 scale 和一个 bias（`cache.py` 第 247–257 行）。CLI 默认 group 64。scale/bias 的 dtype 是量化前 K 的 dtype；下表按 2 字节估计：

```
每元素额外字节 = 2 × 2 / group_size
group 64 → +0.0625
int8 group 64 = 1.0625 字节/元素
int4 group 64 = 0.5625 字节/元素
```

9B 权重的 group 32 不会自动变成 KV 的 group。若有人把 KV group 设成 32，int4 是 0.625 字节/元素。

| 估算 | 9B 每 token | 27B 每 token |
|---|---:|---:|
| bf16/fp16 载荷 | 32 768（32 KiB） | 65 536（64 KiB） |
| int8 裸 | 16 384 | 32 768 |
| int4 裸 | 8 192 | 16 384 |
| int8，group 64，含 scale/bias | 17 408（17 KiB） | 34 816（34 KiB） |
| int4，group 64，含 scale/bias | 9 216（9 KiB） | 18 432（18 KiB） |

把 bf16 载荷乘长度（仍是估算）：

| token 数 | 9B 全注意力 KV | 27B 全注意力 KV |
|---:|---:|---:|
| 4 096 | 128 MiB | 256 MiB |
| 8 192 | 256 MiB | 512 MiB |
| 32 768 | 1 GiB | 2 GiB |
| 65 536 | 2 GiB | 4 GiB |
| 131 072 | 4 GiB | 8 GiB |
| 262 144 | 8 GiB | 16 GiB |

对应的 int4 group-64 估算约是上表的 9216/32768 = 0.28125 倍（9B 在 32 768 token 约 288 MiB，在 262 144 token 约 2.25 GiB）。

线性层是常数，不在「每 token」里：

```
循环状态 = 线性层数 × Hv × 128 × 128 × 4     # float32
conv     = 线性层数 × 3 × conv_dim × 2       # 假设激活是 bf16
conv_dim = 2 × (128 × 16) + (128 × Hv)
```

9B：50 331 648 + 1 179 648 = 51 511 296 字节（49.125 MiB）。27B：150 994 944 + 2 949 120 = 153 944 064 字节（146.8125 MiB）。压这摊状态省不下长上下文的内存，而且 metal kernel 把状态保持在浮点。

权重量级：9B 约 5.28 GiB，27B 约 14.09 GiB。9B 在 32K 的全注意力 KV 估算约 1 GiB，加上大约 49 MiB 线性状态，相对权重还小。262K 的 8 GiB 全注意力 KV 才会和 24 GB 统一内存打架。27B 光权重就约 14 GiB，32K 再加约 2 GiB KV。这是估算，不是这台机器上的实测余量。

LRU 最多再留若干份。4 条上限再加 `4e9` 字节帽。命中时还有一次 deepcopy。这是前缀复用的成本，不是压缩比。

## 5. 给编排器的实验顺序

没有原型。不要在 kiln 后端里 `import mlx`，不要加载这两份权重来「先写个压缩器」，也不要改 `start-mlx.sh` 或 LaunchAgent 副本，直到离线质量过关。下面只是顺序。

1. **先量，再改算法。** 用单独进程、现成的 `mlx_lm.cache_prompt` 或 `mlx_lm.generate`（会加载模型，所以不要打进正在听 8081 的那个进程）。在 4K 和 32K 记下峰值内存，并和上一节的全注意力载荷加 49 MiB 线性状态对照。同时看 HTTP `cached_tokens`：那是前缀 LRU，不是压缩。对不上时先查 256 对齐和 deepcopy，不要发明新 cache。

2. **维持现在的 LRU，不要加份数。** `--prompt-cache-size 4` 和 `4G`（十进制 4e9）已经是线上值。混合 cache 不能裁掉更长的分叉前缀。加份数只会多占内存。

3. **第一件真正会缩小 KV 的事：CLI `--kv-bits`。** 顺序是 8 bit，再 4 bit；`--kv-group-size 64`；`--quantized-kv-start` 先用默认 5000，再试 0。只影响 8 个 `KVCache`。线性状态应几乎不动。比较对象用同一批长提示：针在 8K 和 32K、以及一条 Kiln 多轮前缀。成功的样子是全注意力占用接近上表的 17 KiB 或 9 KiB 每 token，而且检索没有明显变差。失败就停，不要接着上 SnapKV。服务端目前接不上这个开关；在离线结果写清楚之前，不要改 server 参数解析。

4. **不要把旋转窗口和 `--kv-bits` 叠在一起。** `RotatingKVCache.to_quantized` 和批量版本都会抛未实现。`--max-kv-size` 在 `make_prompt_cache` 里对这个模型无效。唯一会换上旋转 cache 的是 `BatchGenerator._make_new_cache`，而且服务端没把参数传进去，`keep` 还是 0（注意力汇点也会丢）。旋转之后，精确注意力只覆盖窗口，更早的 token 只留在 DeltaNet 里。这和模型配置不符（配置没有滑动窗口）。只有第 3 步之后内存仍不够、并且接受这 8 层变短时，才值得单开一项实验。

5. **不要做 SnapKV / PyramidKV / KVPress 的移植，除非第 3 步证明位宽不够。** 移植意味着在 MLX 里重写全注意力的打分和裁剪，只处理那 8 层，并处理批量 cache 的 extract。不是把仓库 pip 进来。Pyramid 的「低层多预算」不能直接套到 DeltaNet 层上。

6. **27B 用同一套代码路径，但不要为了这次实验把它换上 8081。** 它是 16 层全注意力、估算 64 KiB/token（bf16），线性状态约 147 MiB，权重约 14.1 GiB。bit 宽对它更亏得值，但仍只压全注意力层。换模型会停掉当前 9B。

明确声明：**没有部署 KV 压缩原型。** 当前 9B 服务仍是未量化的混合 cache：24 个固定状态的线性层，8 个随 token 增长的全注意力层，外加最多 4 份、合计不超过 4e9 字节的前缀 LRU。

原始摘录：`/Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/raw/A7/`。
