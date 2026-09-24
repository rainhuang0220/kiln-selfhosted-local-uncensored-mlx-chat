# 上下文与压缩（2026-09-24）

没有把实验性的 KV 压缩或 LLMLingua 接到生产。下面按风险从低到高记录已经量到的，和明确没做的。

## 第一层：原文和前缀缓存

用户原文在进模型之前写入消息表。`truncate_messages` 只丢更老的轮次，不丢最新一条 user。最新一条若仍超过 `practical_prompt_budget`（默认 32768），`pack_user_message` 会改写**送进模型的正文**，并在占用信息里带上 `document_pack`。界面在 `web/src/app.tsx` 会显示 packed 前后的 token 数。库里的原文还在。这不是静默丢掉用户文件，但模型确实可能看不到全文。单条 20000 字（约 13464 token）和 20000 token 都低于 32768，按现有估计不会走打包。超过 32768 token 的单条原文仍会被打包，接口可以返回 200。`overflow_policy=error` 只在 `prompt + max_tokens > 262144` 时拒绝，挡不住 32768 这个闸门。

现网 mlx-lm 的 prompt cache 是有效的。同一条 13515 token 的中文题，第一次 TTFT 63.6 s，第二次 0.388 s，服务器只处理了 4/4 个 token，答案不变。短句重复同样是 4/4。缓存键里已经有模型这一维（`model_key`）。槽位 4、字节上限 4 GB。混合缓存里的 `ArraysCache` 不能 trim，所以 Kiln 的 Continue 用丢掉最后一个 token 来避开「精确命中、剩余为空、`insert_segments` IndexError」。这次精确重复剩下 4 个 token，线程没死。零剩余的 `/v1/completions` 路径在 0.31.3 里仍然会杀线程，上游 PR #1581 没有合并。没有在生产上故意复现那次崩溃。

把问题接在一份已经发送过的 20000 字后面，这次**没有**部分命中，服务器把 13515 个 token 又预填了一遍。不能声称任意加长都会复用前缀。

## 第二层：分块检索

Kiln 已有 `pack_document`：按块放进预算，并在正文里标记 `packed=true`。它保留查询句，丢掉放不进预算的块。这是有损的。逐字复述、改代码、合同条款不应该走这条路径。本次没有新写检索索引。20000 字的金额题是整篇直通，三笔数字都对。

## 第三层：Prompt compression

`llmlingua` 不在 `.media-venv`、`.mtplx-venv`、`kiln/.venv` 里。没有 `pip install`，没有下 LLMLingua-2 的 BERT。

上游事实（A8，对仓库核对过）：要显式 `use_llmlingua2=True` 并传入 `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`。默认构造仍是 Llama-2-7b，而且 `use_llmlingua2=False`。`force_reserve_digit` 默认关闭。论文里的压缩倍数没有当成这台机器的结果。压缩器自己的加载时间、内存和耗时都还没量，所以没有端到端数字。

离线回归脚本 `scripts/compress_regression_checks.py` 不加载模型。A8 用 `python3 -S` 跑过：干净文本通过；丢掉数字和日期、丢掉否定并打乱编号、丢掉代码标识符，都会失败。中文应按句删，代码应按块删，不要共用同一种 token 删除。

## 第四层：KV

mlx-lm 0.31.3 对这个 9B 的做法（A7）：24 个线性层用固定大小的 `ArraysCache`，8 个全注意力层用未量化 `KVCache`。随长度涨的是这 8 层。fp16 估算 32 KiB/token，不是仪器读数。20k token 大约 640 MiB，32k 大约 1 GiB，和 footprint 从 5.1 GiB 涨到 8.2 GiB（里面还有多条 prompt cache）同一个数量级。

服务器参数里没有 `--kv-bits`。`--max-kv-size` 只在 `mlx_lm.generate`，不在正在跑的 server。没有滑动窗口。

KVPress、SnapKV、PyramidKV 都挂在 Hugging Face transformers 上。这份混合 MLX cache 不能直接换上。没有写 MLX KV 压缩原型，也没有 A/B。

## 第五层：自动路由

没有做策略路由器。现网实际只有两条：预算内原文直通（加 prompt cache），预算外对单条长文做 `pack_user_message`。各层没有独立开关。要做消融，现在只能改配置里的 `practical_prompt_budget`，不能单独关掉 KV 压缩，因为 KV 压缩不存在。

## 评测

20k 中文金额题是直通，不是压缩后的分数。压缩前后的回归还只有离线字符串检查。18 道短文题在 `benchmarks/longctx/cases.jsonl`，评分器是 `scripts/score_longctx.py`。模型分数以 `benchmark-results/longctx-score.txt` 为准；评分器自检的 0.944 不是模型分。
