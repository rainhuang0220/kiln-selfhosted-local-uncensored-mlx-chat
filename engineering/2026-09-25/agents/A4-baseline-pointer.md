# 优化前基线指针（2026-09-24）

这些是优化前的实测。没有优化后跑次。本文件只转录已有记录，不新跑、不补测、不估算。

来源：

- `kiln/engineering/2026-09-24/performance-baseline.md`
- `kiln/engineering/2026-09-24/benchmark-results/live-20260924T211033.json`
- `kiln/engineering/2026-09-24/benchmark-results/followup-20260924.json`

口径与基线相同：请求打到当时的 `127.0.0.1:8081`，模型目录 `qwen3.5-9b-hauhau-aggressive-mxfp4`，`temperature=0`，流式。本地 token 不含 chat template。服务器 token 取日志里的 `Prompt processing progress` 终值。长上下文每一行 **n=1**。Decode **n=3**。

## 实测

| 项 | 本地 token | 服务器 token | TTFT | 结束后 footprint | n |
| --- | ---: | ---: | ---: | ---: | ---: |
| 20000 个中文字符（`cjk-chars-20000`） | 13464 | 13476 | 65.14044862473384 s | 7678 MB | 1 |
| 20000 token（`tokens-20000`） | 20000 | 20012 | 100.82924791611731 s | 8018 MB | 1 |
| 32k token（`tokens-32000`，本地 32000） | 32000 | 32012 | 169.55934820789844 s | 8192 MB | 1 |
| 精确重复（`cjk20k_exact_repeat`） | — | 4/4 | 0.38817791687324643 s | JSON 未记 | 1 |

基线表把上述 TTFT 写成 65.14 s、100.83 s、169.56 s、0.388 s。20000 个中文字符不是 20000 token。

32k 的服务器 token **32012** 只出现在基线表。`followup-20260924.json` 的 `row32` 有 `local_tokens=32000`、`ttft_s` 和 `footprint="8192"`，没有 prompt progress 行。footprint 单位按基线记为 MB。基线把 32k 结束后的 8192 MB 写成约 8.2 GiB。

精确重复的是 followup 里同一条中文金额题，服务器终值 13515，不是上面 20000 字那一行。第一次（`needles`）TTFT 63.596309875138104 s，footprint 6841 MB，n=1。第二次只重算 4 个 token。

## Decode

短提示，`max_tokens=80`，三次都停在 80 个输出 token。数字来自 `followup-20260924.json` 的 `decodes`。

| 次序 | decode 时间 | tok/s |
| ---: | ---: | ---: |
| 1 | 3.7321299170143902 s | 21.435481019909933 |
| 2 | 3.7578929578885436 s | 21.288525483958914 |
| 3 | 3.7126508746296167 s | 21.5479458482562 |

基线取中位数 **21.44 tok/s**（n=3）。没有另算一个中位数。

## Footprint

同一组记录里，长上下文序列开始前 `tokens-1024` 的 `footprint_before_mb` 是 5069。基线写 MLX footprint 从约 5.1 GiB 涨到 32k 测试后的 8.2 GiB。上表三行的结束后读数是 8018 MB、7678 MB、8192 MB。精确重复那条没有 footprint 字段。

## 没有的东西

没有优化后的对照跑。没有第二组长上下文样本。64k 没有跑。
