# 磁盘依赖图，2026-09-25

可安全删除项：**0**。清理门禁要的是这份可复核依赖图；零条同时满足「本项目遗留、无源码/测试/LaunchAgent/运行进程引用、不是学习模型、身份明确」时，结果就是通过，不要求非零删除。不确定的一律保护。本次没有删除、移动、prune 或重启。没有哈希超过 10MB 的权重。

HEAD `9e2524170366aabcd717cd6b488f5e2a3ed6880d`。主测量 `2026-09-25T13:18:22+08:00`。每个路径单独跑了一次 `du -sh -x`，没有并行。inode 是目录自己的 `device:inode`。APFS clone 用 `getattrlist` 的 `ATTR_CMNEXT_CLONEID`、`CLONE_REFCNT`、`PRIVATESIZE`、`EXT_FLAGS`，不读文件内容。

明细在同目录 `disk-dependency.csv`。30 行全是 `protect`，0 行 `delete`。

## 依赖边

- `~/Library/LaunchAgents/com.kiln.mlx.plist` 启动 `~/Library/Application Support/kiln/start-mlx.sh`，其中 `--model` 写死桌面 9B。仓库 `scripts/start-mlx.sh` 在没有 `data/active-model.env` 时也默认同一目录。该 env 文件不存在。
- PID 1581 的参数指向桌面 9B。`lsof -p 1581 -Fn` 有 76 个 name，没有一个落在 9B、27B、图像、视频、Hugging Face hub 或 `~/.mtplx`。cwd 是 `kiln`（inode `16777232:34656640`），另外打开的是 `kiln/.venv` 里的库和 `/private/tmp/kiln-mlx.log`、`kiln-mlx.err`。9B 权重**没有**被这个进程映射。
- `backend/app/config.py` 指向 Z-Image、FLUX.2、FLUX.1、Wan DiT 文件、Wan aux、Wan MLX、`.media-venv`。
- `backend/app/services/media_runtime.py` 把 `video-wan21-t2v-1.3b-nsfw-src` 当作转换 staging。
- `scripts/start-mtplx.sh` 指向 `~/.mtplx/models` 里的 4B 和 9B，以及 `.mtplx-venv`。
- 桌面 `qwen3.8-27b` 与 `/Users/rainhuang/models/qwen3.8-27b` 是 clone 对。测试里的 `parents[3] / "qwen3.8-27b"` 只解析到桌面那棵。home 绝对路径在 kiln、LaunchAgent、Application Support 里都没有出现。
- Qwen2.5-1.5B 的 snapshot 名字是指向 `blobs/` 的符号链接，跟随之后是同一个 inode，`nlink=1`。`du` 没有把它们算成两份。

## 27B clone

两棵目录都是 `du -sh -x` = `14G`，但三块权重的 private size 都是 0，所以不能把 14G+14G 加成 28G，也不能以为删掉其中一棵就会腾出 14G。`EF_SHARES_ALL_BLOCKS|EF_MAY_SHARE_BLOCKS` = 65，refcnt = 2。clone id 等于 **home** 文件的 inode。

| 文件 | 桌面 inode | home inode / 两边 clone id | 逻辑大小 | 两边 private |
|---|---|---|---|---|
| model-00001-of-00003.safetensors | 34623944 | 34620074 | 5328325648 | 0 |
| model-00002-of-00003.safetensors | 34623914 | 34620076 | 5354185130 | 0 |
| model-00003-of-00003.safetensors | 34623918 | 34620106 | 4450532735 | 0 |

同名的另外 23 个文件同样是全量 clone。唯一例外是 `chat_template.jinja`：桌面 9168 字节、home 8952 字节，clone id 不同，refcnt 都是 1，各有 12288 字节 private。因此 home 不是可以整目录丢掉的纯副本。两棵都保护。Spotlight 只为 9B 的 `model-00001-of-00002.safetensors` 和 Wan DiT 各找到一条路径；这两类的 clone id 等于自身 inode，private size 覆盖逻辑大小。

## 其他核对

按名字在 `/Users/rainhuang/Desktop/models` 下实际存在的是 `image-z-image-turbo-mflux-4bit`、`image-flux1-dev-mflux-4bit`、`image-flux2-klein-4b-mflux-4bit`、`image-flux2-klein-4b-uncensored-te`、`video-nsfw-wan-1.3b`、`video-nsfw-wan-1.3b-mlx`、`video-wan21-t2v-1.3b-aux`、`video-wan21-t2v-1.3b-nsfw-src`。没有同名第二目录。`*.incomplete` 在这三处范围里是 0，不把以前已经 unlink 的碎片再算进可释放空间。

`~/.mtplx` 只列了这些目录和 `du -sh -x`：`Youssofal--Qwen3.5-4B-MTPLX-Optimized-Speed` 2.4G，`Youssofal--Qwen3.5-9B-MTPLX-Optimized-Speed` 8.1G，`session-bank` 548M，`logs` 532K，`metrics` 56K。

9B `config.json` 是 `model_type=qwen3_5`。桌面 27B 同样是 `qwen3_5`，README 的 `base_model` 为 `AEON-7/Qwen3.8-27B-AEON-ULTIMATE-UNCENSORED-BF16`。1.5B 是 `model_type=qwen2`。在 `Desktop/models`、`~/.cache/huggingface`、`~/.mtplx` 里按名字找，跳过 `node_modules`、`site-packages`、`blobs`、`entries`，没有 Qwen3B / Qwen2.5-3B 目录。没找到不等于学习模型已经不在别的路径。

第一轮 walk（不含 home 27B，也不含 kiln 与两个 venv）看了 7786 个普通文件：共享 inode 组 0，共享 clone 组 0。home 27B 是事后按文件名补进图里的对端。未扫描 Documents，也没有把整份 home 的每个文件都做 clone 比对。
