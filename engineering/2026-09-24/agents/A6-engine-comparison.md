# A6：MLX 与 llama.cpp Metal 对照计划

日期：2026-09-24。机器：Apple M4，10 核，统一内存 24.0 GiB（`hw.memsize=25769803776`），macOS 26.5（25F71）。

本文件只记录本机事实和一份尚未执行的对照协议。没有编译 llama.cpp，没有下载或转换权重，没有向 `127.0.0.1:8081` 发送生成请求。原始输出在 `kiln/engineering/2026-09-24/raw/A6/`。

## 1. 本机 MLX

正在听端口的是 PID 1581，不是 Homebrew 的 Python 3.14。命令行是：

`Python -m mlx_lm.server --model /Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4 --host 127.0.0.1 --port 8081 --max-tokens 32768 --temp 1.0 --top-p 0.95 --top-k 20 --decode-concurrency 1 --prompt-concurrency 1 --prefill-step-size 1024 --prompt-cache-size 4 --prompt-cache-bytes 4G`

进程已运行约 13 天，PPID 1，无子进程，监听 `127.0.0.1:8081`。它映射的是 `kiln/.venv`（Python 3.12.12）里的 `libmlx.dylib`、`mlx.metallib` 和 `core.cpython-312-darwin.so`。该 venv 当前元数据是 **mlx-lm 0.31.3**、**mlx 0.32.1**、**mlx-metal 0.32.1**。Homebrew Python 3.14 上也是 mlx-lm 0.31.3 / mlx 0.32.1，但那不是 PID 1581 的环境；系统 `python3.12` 本身没有 `mlx_lm`。

`mlx_lm.server --help`（venv：`python -m mlx_lm server --help`）里和预填、缓存有关的标志：

| 标志 | 帮助文本 | argparse 默认 | PID 1581 实际值 |
| --- | --- | --- | --- |
| `--prefill-step-size` | Step size for prefill processing | 2048 | 1024 |
| `--prompt-cache-size` | 最多保留多少份不同的 prompt KV cache | 10 | 4 |
| `--prompt-cache-bytes` | 这些 KV cache 的字节上限 | 无默认（`None`） | `4G` |

同一条帮助里还有 `--decode-concurrency`（默认 32）和 `--prompt-concurrency`（默认 8）。现网是两者都为 1。`server.py` 在 Metal 可用时把 wired limit 设成 `mx.device_info()["max_recommended_working_set_size"]`。本机另起的 venv 进程（只调用 `device_info()`，没有 `load`）读到该值是 19069665280 字节，约 17.76 GiB。

**`--max-kv-size` 不是 server 标志。** 它在 `mlx_lm generate` 上：`Set the maximum key-value cache size`。源码里这是旋转 KV cache，超长后丢掉旧 token。server 的 prompt cache 是另一件事：按条数和字节缓存多份 prompt KV，不是 `--max-kv-size`。

量化也不在 server 上。权重量化在模型目录里，转换入口是 `mlx_lm convert`：`-q`、`--q-bits`、`--q-group-size`、`--q-mode`（默认 `affine`，可选 `affine`、`mxfp4`、`nvfp4`、`mxfp8`）。运行时、只在 `generate` / `benchmark` 上的相关标志是 `--quantize-activations`、`--kv-bits`（默认不量化 KV）、`--kv-group-size`（函数默认 64）、`--quantized-kv-start`。

现驻模型目录 5.3G。`config.json` 写的是 `quantization = {group_size: 32, bits: 4, mode: mxfp4}`，`model_type` 为 `qwen3_5`，文本侧 32 层、hidden 4096。这是 MLX safetensors，不是 GGUF。

`mlx_lm.benchmark`（0.31.3）默认：`-p` 512、`-g` 1024、`-b` 1、`-n` 5、`--prefill-step-size` 2048。先 warmup 一次，再打 `prompt_tps`、`generation_tps`、`peak_memory`。`prompt_tps = prompt_tokens / 直到第一个生成 token 的时间`，所以这条路径上 **TTFT（秒）= prompt_tokens / prompt_tps**。`generation_tps` 是其后的 decode tok/s。`peak_memory` 是 `mx.get_peak_memory()/1e9`（十进制 GB 的分配器峰值），不是 `footprint` 的 phys_footprint。benchmark 用随机 token id，并关掉 EOS；分词不在计时里。

## 2. llama.cpp：本机没有二进制

查过且都没有：

- `which`：`llama-cli`、`llama-server`、`llama-bench`、`llama-quantize`、`llama.cpp`、`main` 均 not found
- `brew info llama.cpp`：公式存在，**stable 0.5.0 (bottled), HEAD，Not installed**。`brew list` 里也没有 `llama.cpp` 或 `ggml`
- `/opt/homebrew/bin/llama*`、`/opt/homebrew/opt/llama.cpp`、`~/src/llama.cpp`、`/usr/local/bin/llama*`：没有
- `mdfind` 按 `llama-cli` / `llama-server`：空
- 在 `/opt/homebrew`、`/usr/local`、`~/src`、`~/bin`、`~/.local` 和本 models 树里按文件名找 `llama-cli`、`llama-server`、`llama-bench`：没有

因此没有本机 `--version` 可记。cmake 4.3.2 在 PATH 里，但没有运行。

官方 Metal 构建命令来自 `https://github.com/ggml-org/llama.cpp` 的 `docs/build.md`（2026-09-24 通过 `gh api` 读取 master，当时 HEAD `6b790a9c291b5d7af3312bbf9f0c558aa023b13e`）。**下面这段没有执行。** macOS 上 Metal 默认开启，不需要单独的 `-DGGML_METAL=ON`。关闭编译用 `-DGGML_METAL=OFF`；编进 Metal 之后，运行时用 `--n-gpu-layers 0` 可以不用 GPU。

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build
cmake --build build --config Release
```

Homebrew 的 0.5.0 是另一条版本线。以后如果改用 `brew install llama.cpp`，必须单独记下那个版本，不能和上面的 master 文档混成同一次构建。本次两种都没装。

`llama-bench` 的用法也只能引用仓库文档 `tools/llama-bench/README.md`（同一 master），因为本机没有这个二进制。文档默认：`-p` 512、`-n` 128、`-r` 5、`-b` 2048、`-ub` 512、`-ctk/-ctv` 为 f16、`-ngl` 为 -1。`-pg pp,tg` 是「先处理 prompt，再生成」。输出是 pp / tg 的平均 tok/s 和标准差。文档写明：**计时不含分词和采样**。表格有模型体积，没有峰值内存列。

## 3. GGUF

`find /Users/rainhuang/Desktop/models -name '*.gguf' -maxdepth 4` 结果是 **0 个文件**。同一根目录去掉 maxdepth 再找，仍然是 0。没有名字、没有大小可列。公平对照现在做不了 llama.cpp 一侧：既没有二进制，也没有可加载的 GGUF。不要为了补齐这一侧去下载权重。

## 4. 公平对照协议（计划，未跑）

两边都用文档里的单序列基准，而不是现网 HTTP。现网 server 开着 prompt cache（4 条 / 4G）、`temp 1.0`，并且 prefill 步长是 1024，而 `mlx_lm.benchmark` 默认步长是 2048、`llama-bench` 默认 `-n` 是 128。混用这些默认值就不公平。

固定并写进记录的量：

1. **同一 prompt token 数** `P`。建议先用两边文档都默认的 512。输入用已经数好的 token id，不要用一段未分词的文本去比。MLX benchmark 本来就是随机 token id，且 EOS 关掉；llama-bench 的 pp/tg 也不含分词和采样。
2. **同一生成长度** `G`。必须显式设置。MLX benchmark 默认 1024，llama-bench 默认 128。选定一个之后两边都写上：MLX `-g G`，llama-bench `-pg P,G`（同一趟里先 prefill 再 decode）。不要拿单独的 `pp` 跑和单独的 `tg` 跑拼成一次 TTFT。
3. **同一量化档，而不是「都叫 4-bit」。** 跨量化档的数字不能互换。本机 MLX 权重是 **mxfp4、bits 4、group 32**。这不等于 llama.cpp 的 `Q4_K_M`、`Q4_0`、`IQ4_*`，也不等于 MLX 的 `affine` 4-bit 或 `nvfp4`。没有同档 GGUF 就不要出「引擎谁更快」的结论。llama-bench 打印的 `model_type` / 文件名必须和 MLX `config.json` 的 `quantization.mode`、`bits`、`group_size` 一起落盘。
4. **KV cache 同样不量化、同样不截断。** MLX 不传 `--kv-bits`、不传 `--max-kv-size`、不用 `--prompt-cache-file`。llama-bench 保持 `-ctk f16 -ctv f16`。任何一边单独开 KV 量化或旋转 cache，decode 和内存都会变，不能和另一边比。
5. **单并发。** MLX `-b 1`。llama 侧用 `llama-bench` 的单条测试，不要开 `llama-server` 的多 slot，也不要把 MLX 的 `--decode-concurrency` / `--prompt-concurrency` 调到 1 以上。现网虽然已经是 1，但 server 还有 prompt cache，缓存命中会把 TTFT 打穿，不能拿来和冷启动的 llama-bench 比。
6. **预填步长写成同一个数。** MLX `--prefill-step-size` 对齐 llama-bench 的 `-b`。工具默认都是 2048；现网 server 是 1024。对照「引擎」就两边都写 2048（或两边都写 1024），不要一边 1024 一边 2048。`-ub` 只在 llama 侧存在，记录实际值，不要假装 MLX 也有这个旋钮。
7. **重复次数。** 两边都先 warmup（llama-bench 不要加 `--no-warmup`），再各记 5 次（MLX `-n 5`，llama `-r 5`），报告均值。MLX 还要留下每次的 `prompt_tps` / `generation_tps`，不要只留平均。

要报告的三个数，以及它们在两边分别是什么：

- **TTFT。** MLX：`prompt_tokens / prompt_tps`（秒），也就是第一个生成 token 之前的时间。llama-bench 没有名为 TTFT 的列；在 `-pg P,G` 的 prompt 段上，用 `P / pp_tok_per_s` 作为同一口径的 TTFT。两边都要同时写出原始 tok/s，避免只留一个换算后的秒数。
- **decode tok/s。** MLX 的 `generation_tps`。llama-bench 的 tg tok/s（来自同一次 `-pg`，不是另一次 `-p 0` 的空 prompt 生成，除非那一行被明确标成另一个测试）。
- **峰值内存。** 不要把 MLX 的 `peak_memory`（`/1e9` 的分配器峰值）和 llama-bench 的模型文件大小比。llama-bench 文档不报峰值内存。两边在同一次运行期间用同一个 macOS 工具 `footprint -p <pid>` 记录 `phys_footprint` 和 `phys_footprint_peak`。MLX 的 `peak_memory` 可以另列，但要标明单位和口径不同。

GPU 路径：MLX 在这台机器上走 Metal。llama.cpp 按上面的默认 Metal 构建，并且 `-ngl -1`（文档默认，全部层在 GPU）。不要用 `--n-gpu-layers 0` 的 CPU 跑去和 MLX 比。

这三项现在都还不满足：没有 llama 二进制，没有同档 GGUF，而且 PID 1581 仍占着 GPU 内存。协议等编排者放开基准、并且 MLX 进程已退出之后才能跑。本代理没有跑。

## 5. 不要在 PID 1581 还在时再加载 llama.cpp

这是 24GB 统一内存。CPU 和 GPU 用的是同一块物理内存，不是独立显存。

PID 1581 的 `ps` RSS 只有 5408 KB，这不能当成模型已经卸掉。`footprint -p 1581` 给出 phys_footprint **5086 MB**，峰值 **7944 MB**，其中 IOAccelerator（图形）dirty **4872 MB**。权重还在 GPU 上。MLX server 启动时还会把 wired limit 设到约 17.76 GiB 的 recommended working set。

采集当时机器已经紧：空闲页约 0.06 GiB，压缩器占用约 11.0 GiB，wired 约 3.5 GiB。再起一个 llama.cpp Metal 进程（`-ngl -1` 会把 GGUF 也放进同一块 GPU 内存）会和现驻的 mxfp4 9B 抢统一内存。即使将来有一份同档 GGUF，两个模型加上 KV，也不该叠在这 24GB 上。预期是 swap、压缩器继续涨，或者 jetsam。对照必须串行：先停 MLX（本次没有停，也不该由本代理去动 LaunchAgent），确认 footprint 掉下来，再只加载 llama.cpp；测 MLX 时反过来，机器上只有一个引擎。

## 结论

mlx-lm **0.31.3**（现网 venv）能调 prefill 步长和 prompt KV cache；`--max-kv-size` 和 KV/激活量化在 `generate`，不在 server。现驻权重是 mxfp4 group 32，目录 5.3G。llama.cpp 未安装，models 树下没有 GGUF。官方做法是 clone 后 `cmake -B build && cmake --build build --config Release`，macOS Metal 默认开启；该命令未执行。公平数字只能来自同一 token 数、同一生成长度、同一量化档、单并发、冷 cache 的 TTFT、decode tok/s 和同口径峰值内存。跨量化档不能互换。PID 1581 仍占着大约 5GB GPU footprint 的时候，不要在这台 24GB 机器上再加载 llama.cpp。
