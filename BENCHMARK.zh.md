# 推理基准

硬件：Apple M4，24 GB 统一内存。  
模型：Qwen3.8-27B 4bit MLX。  
服务：Python 3.12 虚拟环境里的 `mlx_lm.server`，`127.0.0.1:8081`。

测试脚本：`benchmarks/run_inference.py`（走 HTTP，**不会再加载一份 14GB 权重**）。

```bash
cd kiln
.venv/bin/python benchmarks/run_inference.py --cases A --out benchmarks/baseline/baseline.json
# 更重的用例：
.venv/bin/python benchmarks/run_inference.py --cases B --out benchmarks/inference/b.json
```

| 用例 | 输入 token | 生成上限 |
|---|---:|---:|
| A | 100 | 100 |
| B | 1_000 | 200 |
| C | 4_000 | 200 |
| D | 8_000 | 200 |

D 在 24GB 上可能内存不够。网页正在生成时不要跑 C/D。

解码速度 = `生成token数 / (总时间 - 首字时间)`。流式不算加速。

## 基线 A（关闭思考，2026-08-23）

文件：`benchmarks/baseline/baseline.json`

| 指标 | 数值 |
|---|---|
| 输入 token | 112 |
| 输出 token | 100 |
| 首字时间 | 19.44 秒（含 Metal 预热 / prefill） |
| 解码 | **4.88 tok/s** |
| 总时间 | 39.94 秒 |
| 缓存 token | 0（第一次） |
| 进程 RSS | 约 170–225 MB（**不含** Metal 里那约 14GB 权重） |

你感觉的大约 6.5 tok/s，和预热后的数字是同一量级。

第二次相同请求（`benchmarks/cache/a_second.json`）：`cached_tokens = 111 / 112`，说明跨 HTTP 的前缀缓存**确实命中**。解码 **7.10 tok/s**。缓存有没有用，看 `cached_tokens`，不要只看墙钟首字时间（容易被排队/预热干扰）。

## 优化记录

| 改动 | 预期 | 实测 |
|---|---|---|
| Python 3.14 → 3.12 | 不再 OpenMP 闪退 | 能稳定 import 和起服务 |
| decode-concurrency = 1 | 避免 27B 批量把内存打爆 | 启动参数 |
| mlx 自带前缀 LRU | 第 2 轮起少做 prefill | `cached_tokens` 有数 |
| 思考默认 medium | 避免 xhigh 把额度耗在思考里 | 体验 |
| Server 上 INT8 KV | — | **0.31.3 的 server 没有这个开关** |
| 投机解码 | — | **这颗模型做不了**（`ArraysCache` 不可裁） |
| 缓存份数 10 → 3，上限 1G | 避免复制 10 份混合 cache | **已进** `scripts/start-mlx.sh`；A2/A3 `cached_tokens=108/112`，TTFT 2.67s → 0.74s |
| prefill 步长 512 | 降低 prefill 峰值 | **已进**；1k 输入 prefill **62 tok/s** |

这些改动稳住了 24GB 和首字时间，**没有**把解码从内存带宽墙上挪开。

## 现场（同一颗 27B，旗标已开，2026-08-23 约 01:55）

`benchmarks/live/mlx_lm_now.json`。预热后 3 次 A + 1 次 B，关闭思考。

| | 编码 / prefill | 解码 | 首字 |
|---|---:|---:|---:|
| A（112 入 / 100 出）三次平均 | 冷启动 42 tok/s；命中缓存后 TTFT 0.74s | **6.63 tok/s**（6.58–6.67） | 冷 2.67s / 缓存 0.74s |
| B（1012 入 / 100 出） | **62.1 tok/s** | **6.61 tok/s** | 16.3s |

**平均解码约 6.6 tok/s，没有 30。**

## 为什么这颗 27B 在这台 M4 上到不了 30 tok/s

M4 统一内存带宽大约 120 GB/s。权重 **14.09 GiB**，且 **没有 `mtp.*` 张量**（`mtplx inspect`：`native-ar-only-missing-mtp`）。自回归每步几乎要读完整份主干，上限大约 8–9 tok/s。mlx-lm 0.31.3 加载时还会丢掉 MTP。投机解码仍然会因为 `ArraysCache` 不可裁而报错。

[MTPLX](https://github.com/youssofal/MTPLX) 本身是真的（用模型自带 MTP 头，不另加载草稿模型）。**加速不了当前这个 AEON 目录**。官方 27B Optimized Speed 峰值 **25 GiB**（建议 32GB+）；Bare Speed 峰值约 20 GiB，24GB 很紧，而且主干不是这份 uncensored。

同一台 M4 24GB、同一晚、MTPLX 2.9.1：

| 运行时 | 模型 | Prefill | 解码（A，三次平均） | ≥30？ |
|---|---|---:|---:|---|
| mlx-lm 0.31.3 | AEON 27B 4bit（本目录） | 62 tok/s @1k | **6.63** | 否 |
| MTPLX sustained D2 | Qwen3.5-9B Optimized Speed | 171 tok/s | **24.2** | 否 |
| MTPLX turbo D2 | 同上 9B | 170 tok/s | **23.9** | 否（6bit 走不了 compiled verify） |
| MTPLX turbo D3 | Qwen3.5-4B Optimized Speed | **327 tok/s** | **52.1** | **是** |

B（1012 入）上 4B 是 48.6 解码 / 397 prefill。原始记录：`benchmarks/live/mtplx_9b_now.json`、`mtplx_9b_turbo.json`、`mtplx_4b_turbo.json`。

要跑 ≥30 tok/s 这条路（用 4B 换掉 27B 的质量）：

```bash
npm run start:mtplx          # 127.0.0.1:8082，默认 4B turbo
MTPLX_SIZE=9b npm run start:mtplx
# 让 Kiln 打到它：
MLX_BASE_URL=http://127.0.0.1:8082 npm run dev
```

24GB 上不要同时加载 27B mlx-lm 和 MTPLX。
