# A13 清理计划（只计划，零删除）

时间：2026-09-24 约 20:56–21:05 CST。只读清点加一次带 `--dry-run` 的预览。没有 `rm`，没有 `hf cache prune`（含 `--dry-run`），没有不带 `--dry-run` 的 `hf cache rm`，没有移动，没有改 Kiln 源码或 LaunchAgent。

已执行删除：**0**。批准删除命令：**0**。编排器稍后执行；本文件不是执行许可。

A12 清单文件不存在（`engineering/2026-09-24/agents/` 当时没有 A12）。下面的路径和体积是 A13 自己的只读测量，不代替 A12。

原始记录：`engineering/2026-09-24/raw/A13/`。

## 1. 本机 CLI 与唯一允许的 dry-run 形式

`/opt/homebrew/bin/hf` 与 `/opt/homebrew/bin/huggingface-cli` 都在。`hf version` = **1.27.0**。Kiln `.venv` 里的 Python 包是 `huggingface_hub` **1.28.0**，缓存路径一致，但删除命令以 CLI 1.27.0 为准。

`huggingface-cli` 已废弃：`huggingface-cli --help` 和 `huggingface-cli cache --help` 都只打印改用 `hf`，**不提供** cache 子命令。

`hf cache` 的子命令是 `list`/`ls`、`prune`、`rm`、`verify`。**没有** `hf cache delete`（`hf cache delete --help` 返回 `No such command 'delete'`）。

本版本真正会预览、且默认不删的命令只有：

```bash
# 唯一合法预览形式。TARGETS 必须恰好一个 repo id 或一个 revision hash。
# /opt/homebrew/bin/hf cache rm <单个目标> --dry-run
```

`--dry-run / --no-dry-run` 的默认值是 **no-dry-run**。漏写 `--dry-run` 就会进入真删除（仍会问 `[y/N]`，除非再加 `--yes`）。本计划禁止 `--yes`。

`hf cache prune --dry-run` 在 1.27.0 里存在，但是全局清扫（无引用 revision + `.incomplete`）。任务禁止全局 prune，**因此没有运行**，也不批准以后运行。

帮助原文在 `raw/A13/00-hf-help.txt`。

## 2. 官方 dry-run 流程（对照本机 1.27.0）

`https://huggingface.co/docs/huggingface_hub/guides/manage-cache` 直连超时（解析到 198.18.3.59，30s timeout）。下文引自与本机 CLI 同标签的指南源：`huggingface_hub` **v1.27.0** `docs/source/en/guides/manage-cache.md`（已存 `raw/A13/manage-cache.md`）。「Clean cache from the terminal」原文：

> Mix repositories and revisions in the same call. Add `--dry-run` to preview the impact, or `--yes` to skip the confirmation prompt when scripting:
>
> ```text
> ➜ hf cache rm model/t5-small 8f3ad1c --dry-run
> About to delete 1 repo(s) and 1 revision(s) totalling 1.1G.
>   - model/t5-small:
>       8f3ad1c [main] 1.1G
> Dry run: no files were deleted.
> ```
>
> Both commands support `--dry-run`, `--yes`, and `--cache-dir` so you can preview, automate, and target alternate cache directories as needed.

同节还写了 `hf cache prune` 会删掉「不再被 branch/tag 引用的 revision」以及中断下载留下的 `.incomplete`。`hf cache rm` 本身不碰孤立的 `.incomplete`，除非删掉整个 repo。官方示例里的多目标、`$(hf cache ls -q)` 批量、以及 `-y`，都超出本计划，禁止照抄。

本机按这个流程做了**一次**预览（不是批准）：

```bash
# 已跑过，仅验证；目标仍是 UNKNOWN，禁止去掉 --dry-run
# /opt/homebrew/bin/hf cache rm model/Qwen/Qwen2.5-1.5B-Instruct --dry-run --format human --no-truncate
```

输出（`raw/A13/10-dry-run-NOT-APPROVED.txt`）：`About to delete 1 repo(s) totalling 3.1G`，随后 `Dry run: no files were deleted`（`dry_run: True`）。预览之后 `refs/main` 仍在。

## 3. 分类规则

只使用这四类，外加一条 27B 特例。判不了就 UNKNOWN。UNKNOWN 不删。

| 类 | 含义 | 能否进删除表 |
| --- | --- | --- |
| ACTIVE | 当前进程正在用，或脚本默认就会加载 | 否 |
| PROTECTED | 图像（flux、z-image）、视频（wan）、Qwen 3B 候选、现场 9B，以及它们的 Hub 目录壳 | 否 |
| 非自动过时 | 27B。知道它是什么，但**不得**因为「现在没挂在 :8081」就标成 OBSOLETE | 否 |
| OBSOLETE | 已证明是废弃副本，且不属于上面三类 | 才可以写成注释命令，仍不由 A13 执行 |
| UNKNOWN | 用途未证实，或没有 A12 交叉确认 | 否 |

硬禁止：

- 不删 UNKNOWN。
- 不删图像模型（名字或路径含 flux、z-image、FLUX、klein 图像包）。
- 不删视频模型（wan，含 aux、mlx、src）。
- 不删 Qwen 3B 候选。本次没找到 3B 权重目录；一旦出现，直接 PROTECTED。
- 不删现场 9B：`/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4`。
- 27B 不是自动过时。
- 禁止无范围的 `rm -rf`（没有单一绝对路径，或路径是家目录、缓存根、`models` 根、`Documents`）。
- 禁止全局 cache prune，包括 `hf cache prune --dry-run`。
- 禁止清空 `~/Documents`。Documents 约 538M，深度 2 的 qwen/flux/wan/mlx/huggingface/z-image 名称搜索无命中，里面不是模型库。

每条将来的删除命令必须是注释，且只点名**一个** repo id 或**一个**绝对路径。禁止 `hf cache rm` 一次带多个 TARGETS，禁止 `hf cache rm $(hf cache ls …)`，禁止 `--yes`。

## 4. 现场事实（只读）

- `:8081` 仍是 PID 1581：`mlx_lm.server --model /Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4`。这是现场 9B。没有 `data/active-model.env`。
- 没有 mtplx / mflux 进程。`:8787` 是另一个 Python 监听，本计划不动。`:7777` 不是模型服务。
- 默认 Hub 缓存：`HF_HOME=/Users/rainhuang/.cache/huggingface`，`HF_HUB_CACHE=/Users/rainhuang/.cache/huggingface/hub`。环境变量未覆盖。
- `Desktop/models` 下的权重大文件是普通文件，不是指向 Hub `blobs/` 的符号链接。删 Hub 缓存**不会**卸掉现场 9B，但 Hub 里那些受保护 repo 的空壳仍然不删。
- `hf cache ls` 只列出 1 个完整仓库。另外 8 个目录没有 `snapshots/`，CLI 报 inconsistency 后忽略。Hub 里 **0** 个 `.incomplete`。`hf cache prune` 即使允许跑，也清不到下面模型目录里的残留。

## 5. 分类表

体积来自 `du -sh`（`raw/A13/02-models-root-du.txt`、`06`、`09`）。约数，执行前必须重测该路径。

| 路径或 repo id | 体积 | 分类 | 原因 |
| --- | --- | --- | --- |
| `/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4` | 5.3G | ACTIVE + PROTECTED | PID 1581 正在加载的现场 9B |
| `model/TheCluster/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-MLX-mxfp4` → `…/models--TheCluster--Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-MLX-mxfp4` | 4K，无 snapshots | PROTECTED | 现场 9B 的 Hub 壳。CLI 看不见，不调用 rm |
| `/Users/rainhuang/Desktop/models/qwen3.8-27b` | 14G | 非自动过时 | 本地 4bit 27B。不在 :8081，也**不是** OBSOLETE |
| `model/choppedgarlic/Qwen3.8-27B-AEON-ULTIMATE-UNCENSORED-4bit-MLX` 的 Hub 壳 | 4K | 非自动过时 | 27B 对应空壳 |
| `/Users/rainhuang/Desktop/models/image-flux1-dev-mflux-4bit` | 9.0G | PROTECTED | FLUX.1-dev 图像 |
| `/Users/rainhuang/Desktop/models/image-flux2-klein-4b-mflux-4bit` | 4.4G | PROTECTED | FLUX.2 Klein 图像 |
| `/Users/rainhuang/Desktop/models/image-flux2-klein-4b-uncensored-te` | 16K | PROTECTED | flux 图像相关目录，无大权重，仍不删 |
| `/Users/rainhuang/Desktop/models/image-z-image-turbo-mflux-4bit` | 7.4G | PROTECTED | Z-Image |
| Hub 壳：`AITRADER/FLUX1-dev-mlx-4bit`、`RunPod/FLUX.2-klein-4B-mflux-4bit`、`filipstrand/Z-Image-Turbo-mflux-4bit`、`ponpoke/flux2-klein-4b-uncensored-text-encoder` | 各 4K | PROTECTED | 图像家族空壳 |
| `/Users/rainhuang/Desktop/models/video-nsfw-wan-1.3b` | 2.6G | PROTECTED | Wan |
| `/Users/rainhuang/Desktop/models/video-nsfw-wan-1.3b-mlx` | 12G | PROTECTED | Wan MLX，含约 11G T5 |
| `/Users/rainhuang/Desktop/models/video-wan21-t2v-1.3b-aux` | 11G | PROTECTED | Wan aux（另一份约 11G T5/VAE）。看着像重复，仍是 wan |
| `/Users/rainhuang/Desktop/models/video-wan21-t2v-1.3b-nsfw-src` | 3.1G | PROTECTED | Wan 源权重。不因为旁边已有 nsfw 目录就当废弃 |
| Hub 壳：`NSFW-API/NSFW_Wan_1.3b`、`Wan-AI/Wan2.1-T2V-1.3B` | 各 4K | PROTECTED | 视频空壳 |
| Qwen 3B 候选 | 未找到目录 | PROTECTED（规则预先生效） | `Desktop/models`、`~/.mtplx`、`~/.cache/huggingface`、Downloads/Desktop 深度 3 名称搜索都没有 Qwen 3B 权重 |
| `/Users/rainhuang/.mtplx/models/Youssofal--Qwen3.5-4B-MTPLX-Optimized-Speed` | 2.4G | ACTIVE 能力，不删 | `start-mtplx.sh` 默认 `MTPLX_SIZE=4b`。当前没进程，不是垃圾 |
| `/Users/rainhuang/.mtplx/models/Youssofal--Qwen3.5-9B-MTPLX-Optimized-Speed` | 8.1G | PROTECTED | 另一颗 9B，不是 :8081 那颗，但是文档里的 MTPLX 9B 档。不自动过时 |
| `/Users/rainhuang/.mtplx/session-bank` | 548M | UNKNOWN | MTPLX 会话块，不是权重。不删 |
| `/Users/rainhuang/.cache/huggingface/xet` | 9.5M | UNKNOWN | Hub 的 xet 缓存。不单独 prune |
| `model/Qwen/Qwen2.5-1.5B-Instruct` revision `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`，路径 `~/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct` | CLI 报 3.1G，`du` 2.9G | UNKNOWN | 唯一完整 Hub 仓库。`refs=main`，不是游离 revision。Kiln 源码无引用，`lsof` 无打开者。它是 1.5B，**不是** Qwen 3B 候选。用途未证实，禁止删除 |
| `/Users/rainhuang/Desktop/models/.media-venv` | 1.7G | ACTIVE | 图像/视频运行时 |
| `/Users/rainhuang/Desktop/models/.mtplx-venv` | 455M | ACTIVE | MTPLX 运行时 |
| `/Users/rainhuang/Desktop/models/kiln` | 813M | PROTECTED | 源码与数据，不是清理对象 |
| `~/Documents` | 538M | 禁止整库处理 | 未见模型权重名。禁止任何 Documents 范围的删除 |

图像/视频目录里的 `.incomplete` 在受保护树内部，2026-09-03，`lsof` 未打开。非零文件合计 **2,095,340,084 字节**（约 1.95GiB），主要是 Z-Image 的 `text_encoder` 残留 1,880,399,215 字节。它们不是 OBSOLETE 目标：父目录是 PROTECTED，而且不是 Hub 根缓存，`hf cache prune` 也扫不到。本计划不给这些路径写 `rm`。

## 6. 删除表（已执行 = 0）

没有 OBSOLETE 项，所以没有批准命令，也没有可取消注释的 `rm` / `hf cache rm`。

| # | 分类 | 单一目标 | 命令 | 本次是否执行删除 |
| --- | --- | --- | --- | --- |
| — | — | — | # 无。不生成删除命令 | 否（删除数 0） |

已经跑过、且**不算删除、也不构成批准**的预览只有第 2 节那一条 `hf cache rm model/Qwen/Qwen2.5-1.5B-Instruct --dry-run`。仓库还在。禁止改成不带 `--dry-run` 的形式。

明确不写进表、也不许编排器补上的形状：

```bash
# 禁止：无范围
# rm -rf ~/Documents
# rm -rf /Users/rainhuang/.cache/huggingface
# rm -rf /Users/rainhuang/Desktop/models
# 禁止：全局 prune（本机虽支持 --dry-run，仍不跑）
# /opt/homebrew/bin/hf cache prune
# /opt/homebrew/bin/hf cache prune --dry-run
# 禁止：多目标、跳过确认、命令替换
# /opt/homebrew/bin/hf cache rm model/a model/b --yes
# /opt/homebrew/bin/hf cache rm $(/opt/homebrew/bin/hf cache ls -q) -y
```

## 7. 以后若真要删，回收量怎么量

APFS 上 `df -h` 的 Avail **不能**当成「这次删除释放了多少」。可用空间里可能含 purgeable；克隆块被多个路径共享时，删掉其中一个路径，`du` 的数字也不会全部变成新的空闲。`diskutil apfs list` 这次没有单独打出 Purgeable 行。对照同一时刻的只读基线（约 20:57 CST，`raw/A13/08-disk-and-stubs.txt`）：

- `df -h /System/Volumes/Data`：Size 926Gi，Used 476Gi，Avail 403Gi，Capacity 55%。
- `diskutil info`：Volume Used Space 510.7 GB；Container Free Space 432.3 GB（约等于 403Gi）。

删除**之前**和**之后**各记一次，且只针对那一个绝对路径或那一个 repo 目录：

```bash
# 只测量，不删除
df -h /System/Volumes/Data
diskutil info /System/Volumes/Data | grep -E 'Volume Used Space|Container Free Space'
du -sh <这个单一绝对路径>
```

判定：

1. 释放量以该路径删除前的 `du -sh` 为准，并且删除后该路径必须不存在。
2. 再用 Volume Used Space 的下降做交叉检查，数量级应接近这个 `du`。
3. `df` Avail 的变化只作旁证。Avail 几乎不动，或动了但和 `du` 对不上，都**不要**说成已经腾出了 `du` 那么多空间。
4. 不对 `Documents`、家目录、Hub 根、`Desktop/models` 根做前后 `df` 来冒充单项回收。

Hub 仓库若将来被人工改判，测量路径用 dry-run 打印的 repo 目录（本次 1.5B 是 `/Users/rainhuang/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct`），不要用 `df` 的 3.1G 文案代替 `du`。

## 8. 结论

磁盘不紧（Data 可用约 403Gi）。能占空间的权重要么是现场 9B、图像、视频、27B（非自动过时）、MTPLX 4B/9B，要么是 UNKNOWN 的 1.5B（2.9G）和 session-bank（548M）。按规则，A13 不批准任何删除。编排器在 A12 或其他证据把某一项改判为 OBSOLETE 之前，不要执行删除。
