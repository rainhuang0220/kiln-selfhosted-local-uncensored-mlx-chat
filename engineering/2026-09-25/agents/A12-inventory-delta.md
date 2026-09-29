# A12 清单增量（只读）

2026-09-25 02:06:57 CST。没有删除、移动、截断任何文件，没有 `hf cache prune`，没有遍历 `$HOME`。对照的是 2026-09-24 `agents/A12-disk-inventory.md` 的目录 `du` 字节（`du -k` 的 KiB × 1024）和 `disk-inventory-and-cleanup.md` 里已执行的 11 个 `.incomplete` 删除。本次只核对下面这些路径。

## 范围

存在性、`du -sh` 和 `du -sk`：

- `/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4`
- `/Users/rainhuang/Desktop/models/qwen3.8-27b`
- `/Users/rainhuang/Desktop/models` 下名字里带 flux、z-image、wan 的图像/视频目录（`ls -1` 里一共 8 个）
- `~/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct`

`.incomplete` 只在这 8 个图像/视频目录里 `find -name '*.incomplete'`。没有搜 9B、27B、Hugging Face hub，也没有搜 `$HOME`。

Qwen 3B 这个名字只看了两份目录名单：`ls -1 /Users/rainhuang/Desktop/models` 和 `ls -1 ~/.cache/huggingface/hub`。两份都没加 `-a`。没有再用 `find` 或全文搜索去找 `3B`。

没有重测 `~/.mtplx`、Kiln 源码树或三个虚拟环境。那些不在本次路径里，体积仍以 2026-09-24 的清单为准，这里不更新。

## 路径都在

11 个路径都是目录，没有缺失。

## `du -sh`

macOS `du -sh` 按 1024 进位，到 10 以上会收成整数。所以 14G 仍是昨天的 15,153,344,512 字节（约 14.11 GiB），不是变小。

```
5.3G	/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4
 14G	/Users/rainhuang/Desktop/models/qwen3.8-27b
9.0G	/Users/rainhuang/Desktop/models/image-flux1-dev-mflux-4bit
4.3G	/Users/rainhuang/Desktop/models/image-flux2-klein-4b-mflux-4bit
 16K	/Users/rainhuang/Desktop/models/image-flux2-klein-4b-uncensored-te
5.5G	/Users/rainhuang/Desktop/models/image-z-image-turbo-mflux-4bit
2.6G	/Users/rainhuang/Desktop/models/video-nsfw-wan-1.3b
 12G	/Users/rainhuang/Desktop/models/video-nsfw-wan-1.3b-mlx
 11G	/Users/rainhuang/Desktop/models/video-wan21-t2v-1.3b-aux
3.1G	/Users/rainhuang/Desktop/models/video-wan21-t2v-1.3b-nsfw-src
2.9G	/Users/rainhuang/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct
```

## 和 2026-09-24 清单的字节差

今天的字节是 `du -sk` × 1024。差 = 今天 − 昨天。

| 目录 | `du -sh` | 今天字节 | 昨天字节 | 差 |
| --- | ---: | ---: | ---: | ---: |
| `qwen3.5-9b-hauhau-aggressive-mxfp4` | 5.3G | 5,690,613,760 | 5,690,613,760 | 0 |
| `qwen3.8-27b` | 14G | 15,153,344,512 | 15,153,344,512 | 0 |
| `image-flux1-dev-mflux-4bit` | 9.0G | 9,618,608,128 | 9,618,608,128 | 0 |
| `image-flux2-klein-4b-mflux-4bit` | 4.3G | 4,619,808,768 | 4,686,864,384 | −67,055,616 |
| `image-flux2-klein-4b-uncensored-te` | 16K | 16,384 | 16,384 | 0 |
| `image-z-image-turbo-mflux-4bit` | 5.5G | 5,907,574,784 | 7,935,864,832 | −2,028,290,048 |
| `video-nsfw-wan-1.3b` | 2.6G | 2,838,130,688 | 2,838,130,688 | 0 |
| `video-nsfw-wan-1.3b-mlx` | 12G | 12,707,131,392 | 12,707,131,392 | 0 |
| `video-wan21-t2v-1.3b-aux` | 11G | 11,891,097,600 | 11,891,097,600 | 0 |
| `video-wan21-t2v-1.3b-nsfw-src` | 3.1G | 3,345,694,720 | 3,345,694,720 | 0 |
| `models--Qwen--Qwen2.5-1.5B-Instruct` | 2.9G | 3,098,976,256 | 3,098,976,256 | 0 |

两处非零差额合计 −2,095,345,664 字节。这正好等于昨天 TSV 里 4 个非零 `.incomplete` 的已分配块：

| 昨天已分配块 | 位置 |
| ---: | --- |
| 1,880,399,872 | z-image `.cache` text_encoder |
| 80,809,984 | z-image `.cache` vae |
| 67,080,192 | z-image `.cache` transformer |
| 67,055,616 | flux2 `.cache` vae |

z-image 三块之和 2,028,290,048，flux2 一块 67,055,616，与上面两个目录的 `du` 降幅逐项相同。其余 7 个是 0 字节碎片，删掉也不改变 `du`；wan DiT 和 aux 的目录字节因此仍与昨天相同。

目录 `du` 相同不能证明每个分片的 inode 没换过。本次没有重读 inode，也没有重算单文件 `st_size`。能说的是：这些目录还在，已分配字节除上述两处外与清理前清单一致，两处降幅等于已记录碎片的已分配块。

## `.incomplete` 剩余

在上述 8 个图像/视频目录中，`find -name '*.incomplete'` 没有打印任何路径，`wc -l` 为 **0**。

2026-09-24 清单里这 11 个碎片都在这 8 个目录内。清理记录写的是只 `unlink` 这 11 个普通文件，并在当时复测为 0。本次复测仍是 0，没有新的未完成分片。

## 分类

活权重的类别不改：

- 9B：PROTECTED。现行生产目录，5.3G，字节未变。
- 27B：KEEP-REFERENCE。质量参照，不是默认，14G，字节未变。
- flux1、flux2 klein、z-image、wan DiT、wan mlx、wan aux：PROTECTED。完整权重还在。flux2 与 z-image 变小只来自碎片，父目录不能按目录删。
- `image-flux2-klein-4b-uncensored-te`：仍是 16K，UNKNOWN。
- `video-wan21-t2v-1.3b-nsfw-src`：仍是 3.1G，UNKNOWN。

### Qwen2.5-1.5B：PROTECTED，未知学习模型

路径在，`du -sh` 为 2.9G，字节 3,098,976,256，与昨天相同。

这是相对 A12 原文的分类变更。2026-09-24 把它标成 UNKNOWN，并写明不升成 PROTECTED，理由是 Kiln 源码没有引用、又不能证明没人拿来学习。清理记录已把它留作未确认的学习模型，没有删。本次按给定标准改为 **PROTECTED，未知学习模型**：保留，不当作删除对象，也不把它说成现行 9B 或已识别的 Kiln 依赖。

## 两份 `ls` 里没有 Qwen 3B 目录名

`ls -1 /Users/rainhuang/Desktop/models`：

```
image-flux1-dev-mflux-4bit
image-flux2-klein-4b-mflux-4bit
image-flux2-klein-4b-uncensored-te
image-z-image-turbo-mflux-4bit
kiln
qwen3.5-9b-hauhau-aggressive-mxfp4
qwen3.8-27b
video-nsfw-wan-1.3b
video-nsfw-wan-1.3b-mlx
video-wan21-t2v-1.3b-aux
video-wan21-t2v-1.3b-nsfw-src
```

`ls -1 ~/.cache/huggingface/hub`：

```
CACHEDIR.TAG
models--AITRADER--FLUX1-dev-mlx-4bit
models--choppedgarlic--Qwen3.8-27B-AEON-ULTIMATE-UNCENSORED-4bit-MLX
models--filipstrand--Z-Image-Turbo-mflux-4bit
models--NSFW-API--NSFW_Wan_1.3b
models--ponpoke--flux2-klein-4b-uncensored-text-encoder
models--Qwen--Qwen2.5-1.5B-Instruct
models--RunPod--FLUX.2-klein-4B-mflux-4bit
models--TheCluster--Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-MLX-mxfp4
models--Wan-AI--Wan2.1-T2V-1.3B
```

这两份可见名字里没有 Qwen 3B、Qwen3-3B 或 Qwen2.5-3B。`1.3b` / `1.3B` 是 Wan 视频目录。`qwen3.5` 是 9B，`qwen3.8` 是 27B。`Qwen2.5-1.5B-Instruct` 是上面那个 1.5B。`ls` 没加 `-a`，点目录不在这次名单里，因此这不是全盘否定。没有再往外搜。

## 结论

指定路径全部还在。9B、27B、flux1、三条 wan 活目录、暂存目录、空的 uncensored-te，以及 Qwen2.5-1.5B，已分配字节与 2026-09-24 清单相同。flux2 少 67,055,616 字节，z-image 少 2,028,290,048 字节，合计等于当时 4 个非零 `.incomplete` 的已分配块。图像/视频目录里 `.incomplete` 现在是 0。1.5B 改为 PROTECTED，未知学习模型，体积仍是 2.9G。本次没有删除任何东西。
