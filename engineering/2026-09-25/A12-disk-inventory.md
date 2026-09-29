# A12 磁盘只读盘点

2026-09-25 02:42 CST。只读。没有删除、移动、下载，没有 `hf cache rm`，没有 `hf cache prune`（含 `--dry-run`），没有哈希多 GB 权重。`du` 串行，没有扫 `$HOME`，没有打开 `~/Documents`。

清理执行状态：**not_done**。本文件不是删除 manifest。证据完整、可以删的条目：**0**。

## 卷

`df -h`（模型在 Data 卷，不在只读系统快照上）：

| 挂载 | 设备 | Size | Used | Avail | Capacity |
| --- | --- | --- | --- | --- | --- |
| `/` | `/dev/disk3s1s1` | 926Gi | 12Gi | 406Gi | 3% |
| `/System/Volumes/Data` | `/dev/disk3s5` | 926Gi | 474Gi | 406Gi | 54% |

`/` 是 APFS 系统卷快照，`diskutil info` 写明 Volume Read-Only。Data 卷同时刻：Volume Used 508.8 GB（508800233472 字节），Container Free 436.4 GB（436351131648 字节）。稍后一次 `diskutil apfs list` 的未分配是 436343623680 字节。406 GiB 与约 436 GB 十进制是同一段空闲，不是另一块可删文件。容器总大小 994.7 GB。

## 快照

`tmutil listlocalsnapshots /` 成功，3 个：

- `com.apple.os.update-4C1D511861152C85E75802B39EE6AD3BC57658C0ABD5A4D8E33139D2C5AC6460AA9658B282180F7D28B367811F4D3C63`
- `com.apple.os.update-DEDECEC55622993FB7EF1CB6A97E976433E7F84ECCE5514C9C380AF59534732D`
- `com.apple.os.update-MSUPrepareUpdate`

`diskutil apfs listSnapshots /` 成功，对应 disk3s1s1，三条 Purgeable 都是 No。第一条注明会限制容器最小尺寸。`diskutil apfs listSnapshots /System/Volumes/Data` 成功：`No snapshots for disk3s5`。不建议删这些系统更新快照。

## 方法

macOS `du` 不能同时用 `-s` 和 `-d`（`du -sk -x -d 1` 退出 64）。一层大小用一次 `du -hx -d 1` 和一次 `du -kx -d 1`，没有并行第二份 `du`。逻辑大小 = `du -k` 的 1024 字节块 × 1024。device:inode 来自 `lstat`。`st_dev` 16777232 = lsof 的 `1,16`。

`/Users/rainhuang/Desktop/models` 合计 70G，分配块 73196996 KiB = 74953723904 字节。子目录块之和 73196924 KiB，差 72 KiB，是根上的小文件（`.DS_Store`、两份任务说明）所占块。

## 9B revision

目录没有 `.git`。`config.json` 没有 revision 字段。`model_type` 是 `qwen3_5`，`text_config.model_type` 是 `qwen3_5_text`。量化 `mxfp4`，group 32，4 bit。`config.json` sha256 `5a34660c82a3d83f25e53817e55de9de0fbae2928d0d57ac20aa9a8c15e7bcec`。README sha256 `5a7c7b12c5277acd3d54e79ffa0271020fc47ddf59bc72b0276ac1b802bd0720`。README 不含该 SHA。

历史钉 `a9e5f6d9aebfe8bae436bdd51da14dde5b1b30c9` **能在目录里对上**，不是从脚本单独抄来的：

- 每个 `.cache/huggingface/download/*.metadata` 的第一行都是这个 40 位 SHA。抽查包括 `config.json.metadata` 和两个 safetensors metadata。
- 存在 `.cache/huggingface/trees/a9e5f6d9aebfe8bae436bdd51da14dde5b1b30c9.json`。
- 两个权重的 `st_size` 与该 tree 的 `lfs_size` 一致：5130070299 与 540344562。tree 里记录的 lfs sha256 与 `kiln/scripts/fetch-model.sh` 相同。本次没有重算权重 sha256。

不是逐字节冻结副本：`chat_template.jinja` 现为 9420 字节，mtime 8 月 24 日 02:02；tree 记录是 7759 字节，其余小文件 mtime 是 8 月 23 日 16:51。revision 指 HF 下载元数据里的 commit，不是 git checkout，也不是每个文件都未改过。

## PID 1581

进程仍在。`etime` 13-06:50:01。命令是 `mlx_lm.server --model /Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4`，其余参数与现网一致（temp 1.0，top-p 0.95，prefill-step-size 1024，prompt-cache-bytes 4G，thinking off）。

`lsof -p 1581` 退出 0，76 行。没有一行落在 9B、27B、图像、视频、`~/.mtplx/models` 或 Hugging Face hub。cwd 是 `kiln`（inode 34656640）。打开的是 `kiln/.venv` 里的 mlx / numpy / tokenizers 等库，以及 `/private/tmp/kiln-mlx.log` 和 `kiln-mlx.err`。这些已打开路径标为正在使用，不可删。9B 权重不在 fd 表里，但 `--model` 指向它，仍然保护，不可删。

## `.incomplete`

在 8 个图像/视频目录里 `find -name '*.incomplete'`，行数为 0。**本次未发现。** 不把 2026-09-24 已 unlink 的 11 个碎片再算进可释放空间。当时记录释放逻辑字节 2095340084；flux2 与 z-image 的现尺寸已是删后尺寸。

## Hugging Face CLI

`/opt/homebrew/bin/hf`，`hf version` 为 1.27.0。`huggingface-cli` 存在，但 help 写明已废弃且不再工作，本次没有用它列缓存。

`hf cache --help` 有子命令 `list`（别名 `ls`）、`prune`、`rm`、`verify`。`hf cache ls --help` 有 `--revisions`（默认 `--no-revisions`），**没有** dry-run。`hf cache prune --help` 与 `hf cache rm --help` 有 `--dry-run / --no-dry-run`，默认 `--no-dry-run`。prune 和 rm 都没有执行。

`hf cache ls --revisions --format json` 只打出一条一致缓存：

- `Qwen/Qwen2.5-1.5B-Instruct`，revision `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`，`refs/main` 内容相同，CLI 大小 3.1G（十进制）。`du -sh` 为 2.9G，分配块 3026344 KiB = 3098976256 字节。
- `config.json`：`model_type=qwen2`，`architectures=Qwen2ForCausalLM`，hidden 1536，28 层。纯文本。sha256 `98d2ff8cc47488d08a2b0b3acf4eb99ef210779b42bd48605f6b8e36acdbf670`。快照里是指向 blobs 的符号链接，含 `model.safetensors`。

`--show-warnings` 另外 8 个 repo 因没有 `snapshots/` 被忽略。磁盘上每个约 4 KiB，只有 `refs/`。标红保留。它们不是本次可释放空间。

## Qwen3B 与更小的学习模型

在 `Desktop/models`、`~/.cache/huggingface`、`~/.mtplx` 按目录名找（跳过 `node_modules`、`site-packages`、session-bank 的 `blobs`/`entries`）。没有名为 Qwen3B、Qwen3-3B、Qwen2.5-3B 的目录。名字里带 qwen 的只有：现网 9B、`qwen3.8-27b`、HF 里的 1.5B 与两个 4 KiB stub、MTPLX 的 4B 和 9B。

`*transformer*` 命中的是 venv 里的 Hugging Face `transformers` 包，以及 FLUX / Z-Image 的 `transformer/` 权重子目录，不是学习用小模型。`~/.mtplx/session-bank/blobs/3b` 是两字符分片目录，不是 Qwen3B。

1.5B 按未知身份的小型纯文本学习模型保护。不能把它说成那个没找到的 Qwen3B。这三处没找到，也不等于整机没有；没有扫 Documents，没有扫整个 home 的文件内容。

## 27B

实际目录是 `/Users/rainhuang/Desktop/models/qwen3.8-27b`，不是猜测的别名。`model_type` `qwen3_5`，4-bit affine，group 64。README `base_model` 为 `AEON-7/Qwen3.8-27B-AEON-ULTIMATE-UNCENSORED-BF16`。下载 metadata 第一行 commit `875c8523f13294c90226d0a040f35e04366e83c7`，与 `trees/` 文件名一致。权重 sha256 未重算。

现网 PID 1581 不加载它。`kiln/docs/architecture.md`、`inference-mlx.md`、`BENCHMARK.md`、`benchmarks/run_inference.py`、`backend/tests` 仍指向这个路径。用途未改判，不标废弃。

## 候选表

`protect_or_review` 全部是 protect。歧义和所有权不清的缓存不建议删。

| path | device:inode | logical size | referenced_by | owner_evidence | protect_or_review | reason |
| --- | --- | --- | --- | --- | --- | --- |
| `/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4` | 16777232:34819531 | 5.3G / 5690613760 | PID 1581 `--model`；`media-manifest.md`；`fetch-model.sh` | config `qwen3_5`；HF metadata commit `a9e5f6d9…`；权重尺寸与 tree 一致 | protect | 现网 9B。lsof 未占着权重 fd，进程参数仍指向它。正在使用，不可删 |
| `/Users/rainhuang/Desktop/models/qwen3.8-27b` | 16777232:34623913 | 14G / 15153344512 | architecture / BENCHMARK / tests / `run_inference.py`；现网未加载 | 目录名与 README、metadata commit `875c8523…` 一致 | protect | 确认用途前保留。不标废弃 |
| `/Users/rainhuang/Desktop/models/image-z-image-turbo-mflux-4bit` | 16777232:39763893 | 5.5G / 5907574784 | `config.py` `image_zimage_dir`；manifest 默认图像 | 目录名与设置默认值 | protect | 当前图像功能资产。碎片已不在，父目录不可删 |
| `/Users/rainhuang/Desktop/models/image-flux2-klein-4b-mflux-4bit` | 16777232:39763891 | 4.3G / 4619808768 | `config.py` `image_flux_dir`；manifest 可选图像 | 设置默认路径 | protect | 当前 FLUX 功能资产 |
| `/Users/rainhuang/Desktop/models/image-flux1-dev-mflux-4bit` | 16777232:43496342 | 9.0G / 9618608128 | `generate.tsx` `flux1-dev`；`MODEL.md`；`media.py` / tests | 质量档后端名 | protect | 当前 FLUX.1 质量档资产 |
| `/Users/rainhuang/Desktop/models/image-flux2-klein-4b-uncensored-te` | 16777232:39763892 | 16K / 16384 | 本次未在 `config.py` 找到引用 | 几乎是空目录加 HF cache 标记 | protect | FLUX 相关、身份不完整。歧义保留 |
| `/Users/rainhuang/Desktop/models/video-nsfw-wan-1.3b` | 16777232:39763894 | 2.6G / 2838130688 | `config.py` `video_wan_dit` | DiT 文件路径 | protect | 当前视频 DiT |
| `/Users/rainhuang/Desktop/models/video-nsfw-wan-1.3b-mlx` | 16777232:39893482 | 12G / 12707131392 | `config.py` `video_wan_mlx_dir` | 设置默认路径 | protect | 当前视频 MLX 权重 |
| `/Users/rainhuang/Desktop/models/video-wan21-t2v-1.3b-aux` | 16777232:39763895 | 11G / 11891097600 | `config.py` `video_wan_aux_dir`；`wan_bench.py` | T5/VAE 路径 | protect | 当前视频辅助权重 |
| `/Users/rainhuang/Desktop/models/video-wan21-t2v-1.3b-nsfw-src` | 16777232:39893481 | 3.1G / 3345694720 | `media_runtime.py` 转换时 `rmtree` 再重建 | 代码把它当 staging，未逐文件证明可丢 | protect | 转换脚本会删它，但现内容是否唯一未核对。歧义保留 |
| `/Users/rainhuang/Desktop/models/kiln` | 16777232:34656640 | 816M / 855552000 | PID 1581 cwd；LaunchAgent 与 API | 仓库本身 | protect | cwd 正在使用，不可删。未再拆 node_modules |
| `/Users/rainhuang/Desktop/models/.media-venv` | 16777232:39763897 | 1.7G / 1849155584 | `config.py` `media_python`；`wan_bench.py` | `pyvenv.cfg` 指向该路径，Python 3.12.12 | protect | 图像/视频运行时。正在被配置引用 |
| `/Users/rainhuang/Desktop/models/.mtplx-venv` | 16777232:34758269 | 455M / 476905472 | `docs/框架对比.md`；`start-mtplx.sh` 生态 | `pyvenv.cfg` 指向该路径 | protect | MTPLX 虚拟环境，未证明可丢 |
| `/Users/rainhuang/Desktop/models/.pytest_cache` | 16777232:34749962 | 16K / 16384 | 无直接运行引用 | pytest 缓存目录名 | protect | 体积可忽略。歧义保留，不单列可删 |
| `/Users/rainhuang/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct` | 16777232:34073461 | 2.9G / 3098976256 | `hf cache ls --revisions`；Kiln 源码未引用 | `refs/main` = `989aa798…`；纯文本 Qwen2 | protect | 未知学习模型。标红保留 |
| 8 个缺 `snapshots/` 的 hub stub（9B、27B、FLUX.1、FLUX.2、Z-Image、uncensored TE、Wan DiT、Wan2.1） | 见 JSON | 各 4K / 4096 | CLI warning 忽略；与本地权重大名对应 | 只有 `refs/`，不是第二份权重 | protect | 所有权与 refs 用途未逐个打开核对。标红保留，可释放量可忽略 |
| `/Users/rainhuang/.mtplx/models/Youssofal--Qwen3.5-4B-MTPLX-Optimized-Speed` | 16777232:34779249 | 2.4G / 2567573504 | `start-mtplx.sh`；live benchmark 名 | 目录名；PID 1581 未加载 | protect | MTPLX 速度档。不是 Qwen3B |
| `/Users/rainhuang/.mtplx/models/Youssofal--Qwen3.5-9B-MTPLX-Optimized-Speed` | 16777232:34773986 | 8.1G / 8695230464 | `start-mtplx.sh` | 目录名；PID 1581 未加载 | protect | 另一份 9B，不是现网 mxfp4。不标废弃 |
| `/Users/rainhuang/.mtplx/session-bank` | 16777232:34774525 | 548M / 574799872 | MTPLX 目录布局 | 未读 blob 内容 | protect | 会话数据，身份未核对。标红保留 |
| `/Users/rainhuang/.mtplx/logs` | 16777232:34774538 | 532K / 544768 | MTPLX 布局 | 未读日志正文 | protect | 运行痕迹，不建议删 |
| `/Users/rainhuang/.mtplx/metrics` | 16777232:34774532 | 56K / 57344 | MTPLX 布局 | 未读内容 | protect | 同上 |

根上还有 `.DS_Store`（16777232:34623945，14340 字节）和两份 `Kiln_Grok_Engineering_Mission_2026-09-25` 文档（inode 52400957 / 52400956）。不纳入可删列表。

## 结论

Data 卷 `df` 可用 406Gi。现网 9B 5.3G，27B 目录 `qwen3.8-27b` 14G，图像与视频权重大小见上表，1.5B 2.9G。限定路径里没有疑似 Qwen3B 模型目录。PID 1581 没有打开模型权重路径；它打开的是 `kiln` 工作目录和 `.venv` 库。证据完整可删的条目是 0。没有执行清理。
