# A12 磁盘清单（只读）

2026-09-24。没有删除、移动、截断任何文件，也没有运行 Hugging Face cache 的 delete 或 prune。本文件只分类，不执行清理。编排者决定下一步。

明细表：`/Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/raw/A12/inventory.tsv`（123 行，制表符分隔）。

## 磁盘空间

`df -h /` 看的是密封系统快照，不反映模型所在的数据卷。两边都记了。

扫描开始：

```
/dev/disk3s1s1   926Gi    12Gi   403Gi     3%    459k  4.2G    0%   /
/dev/disk3s5     926Gi   476Gi   403Gi    55%    5.4M  4.2G    0%   /System/Volumes/Data
```

扫描结束、TSV 写入之后：

```
/dev/disk3s1s1   926Gi    12Gi   405Gi     3%    459k  4.2G    0%   /
/dev/disk3s5     926Gi   476Gi   405Gi    55%    5.4M  4.2G    0%   /System/Volumes/Data
```

报告写完后再看一次 `/`，`Avail` 又回到 403Gi，`Used` 仍是 12Gi。全程没有删文件。`Avail` 在 403Gi 与 405Gi 之间来回，是 APFS 可清除空间的波动，不是这次扫描释放或占用的模型体积。

## 范围和做法

扫了这些根，没有 `find /`，没有遍历整个 `$HOME`：

- `/Users/rainhuang/Desktop/models`（`du -h -d 1` 后按模型目录再往下）
- `~/.cache/huggingface`（存在）。`~/Library/Caches/huggingface` 不存在
- `~/Library/Application Support/kiln`（56KiB 脚本，无权重）
- `~/.mtplx`（不在最初三处路径里，但是 `kiln/scripts/start-mtplx.sh` 的 `MTPLX_CACHE`，属于 mlx 模型缓存，因此纳入）
- `~/Documents` 只做了 `du -h -d 1`。深度 1 的目录名里没有 models、hf、mlx、qwen，没有打开任何个人文档内容。`~/Library/Mobile Documents` 不存在

`~/.cache/mlx`、`~/.cache/mlx_lm`、`~/Library/Caches/mlx` 都不存在。

命令都加了 `nice -n 15`。身份只看了 `config.json` / README 开头，没有读权重内容。例外：为了判断暂存目录是不是同一份字节，对三对文件做了 `cmp -s`（见下文）。`cmp` 不改内容和 mtime，但会刷新 atime。TSV 里这几个文件的 atime 是 2026-09-24 21:01 CST，是这次比对留下的，不是应用当天加载。

TSV 列：`path, bytes, du_bytes_if_measured, inode, nlink, mtime, atime, kind, model_id_guess, classification, evidence`。

- 文件行的 `bytes` 是 `st_size`。`du_bytes_if_measured` 是 `st_blocks * 512`（已分配字节）
- 目录行的 `bytes` 只是目录项本身的大小，内容体积在 `du_bytes_if_measured`，等于 `du -k` 的 KiB 乘 1024
- `mtime` / `atime` 是 Unix 秒。下面写的日历时间是 CST
- 大于等于 100MB 的权重都有独立行。另外列入了范围内的 `.safetensors`、`.pth`、`.incomplete`，以及文本模型的 `config.json` / `tokenizer.json` / `tokenizer_config.json` / `model.safetensors.index.json`
- 没有 `.gguf`。`.npz` 只出现在虚拟环境的 numpy/scipy/matplotlib 测试数据里，不是模型，没有逐个列入

目录的 `nlink` 大于 1 是子目录计数，不是硬链接。下面说的「nlink=1」指文件。

## 互斥根目录（不要和子目录相加）

| 路径 | du | 说明 |
| --- | ---: | --- |
| `/Users/rainhuang/Desktop/models` | 77,046,038,528（约 71.8 GiB） | 含模型、Kiln 源码、三个虚拟环境 |
| `~/.cache/huggingface` | 3,108,962,304（约 2.90 GiB） | 几乎全是 Qwen2.5-1.5B 的 blobs |
| `~/.mtplx` | 11,838,205,952（约 11.0 GiB） | 4B+9B 权重约 10 GiB，session-bank 约 548 MiB |
| `~/Library/Application Support/kiln` | 57,344 | 无权重 |
| `~/Documents` | 564,543,488（约 538 MiB） | 未下钻，不是模型树 |

这三个模型根互不相交。把它们的 du 加在一起约 92.0 GiB，这是「扫到的树有多大」，不是可回收空间，也不能再和表里的子目录或 TSV 文件行相加。

`Desktop/models` 的一级子目录 du（KiB×1024）之和比父目录少 16 KiB，差额是 `.pytest_cache`。父目录没有藏着未列出的大块。

| 子目录 | du 字节 | 分类 |
| --- | ---: | --- |
| `qwen3.5-9b-hauhau-aggressive-mxfp4` | 5,690,613,760 | PROTECTED（分词器/配置为 ACTIVE） |
| `qwen3.8-27b` | 15,153,344,512 | KEEP-REFERENCE |
| `image-flux1-dev-mflux-4bit` | 9,618,608,128 | PROTECTED |
| `image-flux2-klein-4b-mflux-4bit` | 4,686,864,384 | PROTECTED（内含一块 OBSOLETE 碎片） |
| `image-flux2-klein-4b-uncensored-te` | 16,384 | UNKNOWN |
| `image-z-image-turbo-mflux-4bit` | 7,935,864,832 | PROTECTED（内含 OBSOLETE 碎片） |
| `video-nsfw-wan-1.3b` | 2,838,130,688 | PROTECTED |
| `video-nsfw-wan-1.3b-mlx` | 12,707,131,392 | PROTECTED |
| `video-wan21-t2v-1.3b-aux` | 11,891,097,600 | PROTECTED |
| `video-wan21-t2v-1.3b-nsfw-src` | 3,345,694,720 | UNKNOWN |
| `kiln` | 852,578,304 | UNKNOWN（源码，不是权重） |
| `.media-venv` | 1,849,155,584 | UNKNOWN（被 `media_python` 引用） |
| `.mtplx-venv` | 476,905,472 | UNKNOWN（被 `start-mtplx.sh` 引用） |

`kiln` 里面大的不是权重：`.venv` 536,244,224（`start-mlx.sh` 用它跑 `mlx_lm.server`），`web/node_modules` 164,229,120，`data` 82,345,984（含生成输出）。`kiln/data/active-model.json` 不存在。现行模型以 LaunchAgent 脚本为准。

## 分类怎么落

没有找到名字含 `3B`、`3b` 或 `qwen3-3` 的模型目录。几 GB 的 Qwen 都能对上身份，没有「像 3B 但说不清」的目录：

- 4B：`hidden` 2560、32 层，README 写 `base_model: Qwen/Qwen3.5-4B`
- 生产 9B：`hidden` 4096、32 层、mxfp4
- MTPLX 9B：同样 4096/32 层，但是 6-bit，另外有 vision 和 mtp
- 27B：`hidden` 5120、64 层
- 1.5B：`Qwen2ForCausalLM`，`hidden` 1536、28 层

`~/.mtplx/session-bank/blobs/3b` 只是哈希前缀目录，不是 Qwen 3B。

### PROTECTED：现行 9B

目录 mtime 2026-08-23 17:00 CST。

`~/Library/Application Support/kiln/start-mlx.sh` 和 `kiln/scripts/start-mlx.sh` 默认都是：

`/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4`

`kiln/backend/app/config.py` 的 `model_path`、`docker-compose.yml` 的默认挂载、`MODEL.md` 钉扎的修订 `a9e5f6d9aebfe8bae436bdd51da14dde5b1b30c9` 都指向同一模型。Hub 里 `models--TheCluster--.../refs/main` 就是这个修订，而且没有 blobs，不是第二份 5.3G。

| 文件 | 字节 | inode | 分类 |
| --- | ---: | ---: | --- |
| `model-00001-of-00002.safetensors` | 5,130,070,299 | 34819746 | PROTECTED |
| `model-00002-of-00002.safetensors` | 540,344,562 | 34819737 | PROTECTED |
| `config.json`、`tokenizer.json`、`tokenizer_config.json`、`model.safetensors.index.json` | 合计 20,091,788 | 见 TSV | ACTIVE |

两片权重合计 5,670,414,861。目录里的 `.cache` 只有约 60KiB 的 revision json 和 `*.metadata`，不是另一份权重。量化是 mxfp4、group 32，和下面的 MTPLX 9B 不是同一个检查点。

### KEEP-REFERENCE：27B

`/Users/rainhuang/Desktop/models/qwen3.8-27b`，目录 mtime 2026-08-22 19:04 CST。README 写的是 AEON-7 Qwen3.8-27B 的 4-bit MLX（affine，group 64）。Hub 名是 `choppedgarlic/Qwen3.8-27B-AEON-ULTIMATE-UNCENSORED-4bit-MLX`，那里只有 `refs/main=875c8523f13294c90226d0a040f35e04366e83c7`，没有 blobs。

三片逻辑和是 15,133,043,513 字节（14.09 GiB），和 `BENCHMARK.md` 一致：

- `model-00001-of-00003.safetensors` 5,328,325,648，inode 34623944
- `model-00002-of-00003.safetensors` 5,354,185,130，inode 34623914
- `model-00003-of-00003.safetensors` 4,450,532,735，inode 34623918

分词器和配置一并标 KEEP-REFERENCE。它不是现行 `start-mlx.sh` 的默认模型，也不是已证明的旧文本副本或失败下载，所以不标 OBSOLETE。

### PROTECTED：MTPLX 文本模型

`~/.mtplx/models`，2026-08-23 02:09 一带。

- `Youssofal--Qwen3.5-4B-MTPLX-Optimized-Speed`：du 2,567,573,504。`model.safetensors` 2,367,238,661。`start-mtplx.sh` 默认这个。`mtp.safetensors`（86,701,062）和 `mtp/weights.safetensors`（86,701,040）差 22 字节，inode 不同，不是硬链接，两份都当模型组件留下，不当成可合并副本
- `Youssofal--Qwen3.5-9B-MTPLX-Optimized-Speed`：du 8,695,230,464。分片 5,358,172,442 + 1,918,175,495，另有 `model-vision.safetensors` 912,058,025 和 `mtp.safetensors` 486,582,837。`MTPLX_SIZE=9b` 会用到。6-bit，不是生产 mxfp4 的副本

### PROTECTED：图像和视频

`config.py` 直接引用这些路径。`docs/media-manifest.md` 把 z-image 标成默认图像，flux2 标成可选，wan 的 DiT / MLX / aux 都在用。flux1 是 Image Quality 后端。

| 目录 | 角色 | 大文件逻辑字节（不含 .incomplete） |
| --- | --- | ---: |
| `image-z-image-turbo-mflux-4bit` | 默认图像 | 5,891,426,229 |
| `image-flux1-dev-mflux-4bit` | flux1-dev | 9,612,501,971（与仓库记录的 4-bit 包大小一致） |
| `image-flux2-klein-4b-mflux-4bit` | 可选图像 | 4,608,176,998 |
| `video-nsfw-wan-1.3b` | DiT 源 `wan_1.3B_exp_e14.safetensors` | 2,838,077,328 |
| `video-wan21-t2v-1.3b-aux` | T5 pth + VAE pth | 11,361,920,418 + 507,609,880 |
| `video-nsfw-wan-1.3b-mlx` | 运行时 mlx | t5 11,361,845,505；model 837,683,487；vae 507,591,226 |

T5 的 pth 和 mlx 的 safetensors 差 74,913 字节，VAE 的 pth 和 mlx safetensors 也差一截。它们是源和转换结果，不是同一个 blob，两边都是活权重。已分配块和逻辑大小比都是 1.000，看不出稀疏或压缩少算。

### UNKNOWN：转换暂存，不是 OBSOLETE

`/Users/rainhuang/Desktop/models/video-wan21-t2v-1.3b-nsfw-src`（du 3,345,694,720）。

`kiln/backend/app/services/media_runtime.py` 的 `_convert_wan` 在转换前会 `rmtree` 这个目录，再 `copytree` aux，并把 DiT `copy2` 成 `diffusion_pytorch_model.safetensors`。它不是 Kiln 旧文本模型，也不是失败下载，按给定标准不能标 OBSOLETE。活文件在 DiT 目录、aux 和 mlx 目录。

`cmp -s` 退出码 0，逐字节相同，但 inode 不同、nlink 都是 1：

| 暂存 | 源 | 字节 | inode（暂存 / 源） |
| --- | --- | ---: | --- |
| `diffusion_pytorch_model.safetensors` | `video-nsfw-wan-1.3b/wan_1.3B_exp_e14.safetensors` | 2,838,077,328 | 39893485 / 39819989 |
| `Wan2.1_VAE.pth` | `video-wan21-t2v-1.3b-aux/Wan2.1_VAE.pth` | 507,609,880 | 39893484 / 39878787 |
| `config.json` | aux 的 `config.json` | 249 | 见 TSV |

两边的 `st_blocks` 都报满尺寸。APFS clone 不会让 nlink 变 2，这次也没有读到 clone id，所以不能证明删掉暂存能腾出 3.1 GiB，也不能证明它不占空间。不要把这 3.1 GiB 加进可回收合计。

### UNKNOWN：空的 uncensored 文本编码器

`image-flux2-klein-4b-uncensored-te` 只有 16 KiB：`.DS_Store`、`CACHEDIR.TAG`、`.gitignore`，以及两个空目录。没有权重，也没有带体积的 `.incomplete`。Hub 上 `models--ponpoke--flux2-klein-4b-uncensored-text-encoder` 只有 `refs/main=633217e588e4c0bc76619052e05d3ce0e057cd83`，没有 blobs。Kiln 的 config 和媒体代码没有引用它。这像一次没写下文件的下载，但没有把整个主目录搜完，不能证明没有任何别的项目还指着这个名字，所以保持 UNKNOWN，而不是 OBSOLETE。体积可以忽略。

### UNKNOWN：Qwen2.5-1.5B

`~/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct`，du 3,098,976,256。`refs/main=989aa7980e4cf806f80c7fef2b1adb7bc71aa306`。config 是 `Qwen2ForCausalLM`。Kiln 源码里没有引用。它是小型纯文本模型，不能证明「没人拿来学习」，所以不标 OBSOLETE，也不升成 PROTECTED。

blobs 里的权重大文件：

`blobs/dd924a11b4c220f385b51ffa522daea7c9f3d850e31b162bb5661df483c6d3ee`  
3,087,467,144 字节，inode 34073559，nlink=1，mtime 2026-08-20 22:51 CST。

`snapshots/.../model.safetensors` 是 76 字节的符号链接，指向这个 blob。`snapshots` 的 du 是 0，因为 du 不跟随符号链接。仓库 du 已经包含 blob。把链接行和 blob 行再加一次就会双计。其余 6 个 blob 是分词器和配置，同样只有符号链接，没有第二份。

其他 Hub 仓库（FLUX、Z-Image、Wan、TheCluster、choppedgarlic、RunPod、ponpoke）都只有 `refs/main`，没有 blobs。Desktop 上的 local_dir 才是权重。这些 4KiB 指针不是第二份模型。

### OBSOLETE：只有 `.incomplete` 碎片

11 个文件，唯一标成 OBSOLETE 的集合。文件名以 `.incomplete` 结尾，是 Hugging Face 没下完的碎片。同目录里已经有完整的 safetensors 或 pth，Kiln 配置指向那些完整文件，不指向这些碎片。7 个是 0 字节。有体积的 4 个：

| 字节 | 位置 |
| ---: | --- |
| 1,880,399,215 | `image-z-image-turbo-mflux-4bit/.cache/.../text_encoder/...incomplete` |
| 80,809,657 | 同目录 `vae/...incomplete` |
| 67,079,587 | 同目录 `transformer/...incomplete` |
| 67,051,625 | `image-flux2-klein-4b-mflux-4bit/.cache/.../vae/...incomplete` |

有体积碎片的逻辑和是 2,095,340,084（约 1.95 GiB）。已分配块合计 2,095,345,664。inode 都独立，nlink=1，尺寸也和旁边已经完成的分片对不上（例如 z-image 文本编码器碎片 1,880,399,215，完成的两片是 2,135,435,096 + 127,582,112）。mtime 在 2026-09-03，atime 在 2026-09-07，不是这次扫描刷的。

即便如此，也没有 clone id，不能把这 1.95 GiB 写成已经核实的可回收合计。它们的父目录仍然是 PROTECTED，不能按目录删。z-image 的 `.cache` du 是 2,028,371,968，flux2 的 `.cache` du 是 67,121,152，大头就是这些碎片；完成模型（9B、27B、flux1、wan）的 `.cache` 只有几 KiB 到几十 KiB 的元数据。

0 字节碎片在 wan DiT、wan aux、z-image 的 download 目录里，腾不出空间。

## 硬链接、clone、为什么没有可回收合计

范围内权重大于等于 100MB 的文件，以及 TSV 里的全部文件行：nlink 都是 1，没有两个路径共用同一个 inode。不存在 POSIX 硬链接造成的重复计数。

APFS clone 不会体现在 nlink 上。本次没有读到 clone id。暂存目录和源文件逐字节相同，但两边都报了满的已分配块，所以 du 会把两边都算进去。物理上是两份还是写时复制，未证实。

因此：

- 不把目录 du、文件逻辑字节、暂存目录、`.incomplete`、符号链接和 blob 加总成一个「可回收」数字
- 唯一在分类上允许称为失败下载的，是上面 11 个 `.incomplete`。即便是它们，也只报告逻辑体积，不报告可回收合计
- 27B、生产 9B、MTPLX 4B/9B、全部 flux / z-image / wan 活权重、1.5B、空的 uncensored-te 目录、三个虚拟环境、Kiln 源码，都不要按这次清单当作垃圾

session-bank：7,449 个 blob，文件逻辑和 554,388,480，最大单文件 2,097,152，du 574,799,872。不是权重，标 UNKNOWN。
