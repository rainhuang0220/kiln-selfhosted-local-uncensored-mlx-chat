# 磁盘清单和清理（2026-09-24）

完整分类在 `agents/A12-disk-inventory.md`，逐文件表在 `raw/A12/inventory.tsv`。这里只记总控执行过的删除和必须留下的东西。

## 怎么量的

没有把目录 `du`、逻辑大小和 Hugging Face blob 加总成「可回收空间」。APFS clone 用 `nlink` 看不出来。大文件 `nlink` 都是 1。

互斥的根（A12，不要再加子目录）：

| 根 | 大约 |
| --- | ---: |
| `/Users/rainhuang/Desktop/models` | 71.8 GiB |
| `~/.cache/huggingface` | 2.9 GiB |
| `~/.mtplx` | 11.0 GiB |

`df` 在只读扫描前后，数据卷 Used 都是 476 GiB 量级，Avail 在 403–405 GiB 之间晃，那不是扫描删出来的。

## 保护

| 对象 | 分类 | 动作 |
| --- | --- | --- |
| `qwen3.5-9b-hauhau-aggressive-mxfp4`（5.3G） | 现行生产 | 保留。清理后 `model-00001-of-00002.safetensors` 仍是 5130070299 字节 |
| `qwen3.8-27b`（14G） | 质量参照 | 保留 |
| flux、z-image、wan 的完整权重 | 图像/视频生产 | 保留。清理后这些目录里仍有 16 个 safetensors/pth，z-image 的 text_encoder、transformer、vae 子目录还在 |
| `Qwen/Qwen2.5-1.5B-Instruct`（HF 缓存约 2.9G） | 小型纯文本，身份未证明是废弃 | 保留。没有 Qwen 3B 目录，这个 1.5B 按未确认的学习模型处理 |
| MTPLX 4B / 9B | 别的运行时在用 | 保留 |
| `video-wan21-t2v-1.3b-nsfw-src` | 和源文件大小相同，clone 未证实 | UNKNOWN，未删 |
| `image-flux2-klein-4b-uncensored-te` | 16 KiB 空壳，别的项目是否引用未搜完 | UNKNOWN，未删 |

## 删了什么

只删了 11 个路径，每一个都是普通文件，文件名以 `.incomplete` 结尾，位于图像或视频目录的 Hugging Face `download/` 缓存里，不在 9B、27B 或 Kiln 仓库下。同目录里已经有完整权重。清单先写到 `raw/cleanup/incomplete-manifest.json`，结果在 `raw/cleanup/delete-result.json`。没有 `rm -rf`，没有 `hf cache prune`。

逻辑字节合计 **2,095,340,084**（约 1.95 GiB）。其中大的四块是 z-image text encoder 未完成分片 1,880,399,215 字节、vae 80,809,657、transformer 67,079,587，以及 flux2 vae 67,051,625。其余 7 个是 0 字节。

`diskutil info /System/Volumes/Data`：

| | Volume Used | Container Free |
| --- | ---: | ---: |
| 删除前 | 510.8 GB | 431.1 GB |
| 删除后 | 508.7 GB | 433.2 GB |
| 差 | **−2.1 GB** | **+2.1 GB** |

`df` 的 Used 从 476 GiB 到 474 GiB，Avail 从 402 GiB 到 403 GiB。和逻辑删除量一致，不是 purgeable 分类变化。

这些碎片可以重新下载：它们是 Hugging Face 下到 `local_dir` 时留下的未完成分片，完整文件已经在对应的 `text_encoder`、`transformer`、`vae` 目录里。不需要为了 Kiln 再下一次。

## 清理之后的服务

没有重启 LaunchAgent。

- `GET 127.0.0.1:8081` 非流式短句返回 `kiln-after-cleanup`，`finish_reason=stop`，2.57 s。
- `GET 127.0.0.1:8787/health` 仍是 `ok`，inference ready，chat `running`，模型名不变。
- 上述目录里 `.incomplete` 剩余 0 个。

27B、1.5B、图像和视频的完整文件都没有动。
