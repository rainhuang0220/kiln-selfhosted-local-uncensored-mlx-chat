# 2026-09-24 状态

生产进程没有换模型，没有重启。PID 1581 仍在 `127.0.0.1:8081`。

## 已实施

- 只读基线：硬件、LaunchAgent、版本、Git、请求链路。见 `system-audit.md`。
- 真实生成：20000 个中文字符、20000 token、32000 token。金额题答案正确。见 `performance-baseline.md`。
- 精确前缀缓存：13515 token 的第二次请求 TTFT 0.388 s，只重算 4 个 token。
- Decode：n=3，中位数 21.4 tok/s。
- 18 道短文：评分器 12/18。其中几条是空格或 Markdown，英文跨段把 dock 3 说成 dock 7。
- 公网：静态页 200；未登录 `POST /chat` 401，且 401 来自本机 API。
- 删除 11 个 `.incomplete` 碎片，卷已用空间减少 2.1 GB。9B、27B、1.5B、图像和视频完整权重还在。见 `disk-inventory-and-cleanup.md`。
- 能力审计：没有新装远程技能。见 `capability-audit.md`。

## 只做了实验或测量，没有进生产

- 长上下文速度表（n=1）。
- 18 题短文。
- Prompt cache 在「文档后再加问题」时没有部分命中。
- 离线压缩回归脚本。没有加载 LLMLingua。
- KV 字节估算。没有 KV 压缩原型。

## 没做

- 替换 9B。4B 在 MTPLX 目录里，没有加载。
- llama.cpp。
- 升级 mlx-lm 到 git main（`/health` 仍是无条件 200）。
- 64k。
- 拒答率。
- 故意用精确 `/v1/completions` 命中去打死生成线程。A3 的复现脚本要 `KILN_ALLOW_REPRO=1`，跑完必须重启 LaunchAgent。
- 把仓库 `scripts/start-mlx.sh`（temperature 0.6）装回 LaunchAgent。现网是 Application Support 里的 temperature 1.0。回滚目标是后者。

## 回滚

模型文件的删除只涉及列出的 11 个 `.incomplete` 路径，完整权重还在，不需要为了 Kiln 重下。服务参数没改。要回到清理前的磁盘，只能重新开始那些未完成的 Hugging Face 下载，没有别的配置可回滚。
