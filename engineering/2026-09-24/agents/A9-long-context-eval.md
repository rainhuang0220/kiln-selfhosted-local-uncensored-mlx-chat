# A9 长上下文离线评测

这次只写了可审阅的离线题库和评分器。没有调用生成接口，没有下载模型，没有改 `backend/` 或 `web/`。下面的 0.944 是评分器自检，不是模型分数。

## 交付

- 题库：`/Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/benchmarks/longctx/cases.jsonl`（18 条，UTF-8 JSONL，整文件约 53KB，单条小于 8KB）
- 评分器：`/Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/scripts/score_longctx.py`（只读本地文件，无网络）
- 假预测：`/Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/raw/A9/predictions.jsonl`
- 这次运行的原文：`/Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/raw/A9/score-run.txt`

每条字段：`id`、`category`、`input`、`question`、`gold`、`scoring_rule`（`exact` / `contains_all` / `ordered`）、`tags`、`generator_note`。`tags` 里有 `en` 或 `zh`。中英都有，九类都有，三种规则都有。

`question` 不写进 `input`。以后拼提示时再把题目接在材料后面，避免题目把事实又贴到文末，把“开头 / 结尾 / 中段”测坏。标准答案字符串不出现在题干里。

建议以后的用户消息（本次不要发）：

```text
阅读材料并只按题目作答。不要复述材料。

材料：
{input}

题目：
{question}
```

预测文件是 JSONL，每行 `{"id": "...", "output": "..."}`。评分器不看思考过程，只看 `output`。

## 现有 Kiln 基准不覆盖什么

仓库里已有的基准测速度、缓存、对话表面质量和生图遵循，没有这套“给材料、对标准答案”的长上下文题。

| 已有 | 实际在测 | 不覆盖 |
|---|---|---|
| `kiln/benchmarks/run_inference.py`，说明在 `kiln/BENCHMARK.md`、`kiln/BENCHMARK.zh.md` | HTTP SSE 的 TTFT、prefill、decode tok/s、RSS、前缀缓存。A/B/C/D 约 100 / 1k / 4k / 8k token，正文是重复的 “quick brown fox” | 没有事实位置，没有标准答案，8k 也只说明慢不慢，不说明还记不记得 |
| `kiln/benchmarks/dialogue_reliability/run_context.py` | 冷提示按字符垫到最长约 3.2 万，以及多轮热 TTFT。垫文是重复的“旧书店”句子 | 同样只测时延。垫文里没有可抽取的针 |
| `kiln/benchmarks/dialogue_reliability/run_quality_eval.py` 与 `summarize_quality.py` | 真模型多轮。场景 A 关系、B 动作、C 日常、D 短回复、E 打断。指标是重复、n-gram、开头结尾多样性、低信息跟进、协议失败、TTFT | 要打正在跑的 API。不判某条事实对不对，也不测代码检索、日期金额、近形人名、步骤重排 |
| 同目录其余 `run_prefill_*.py`、`run_prompt_cache*.py`、`run_baseline.py`、`run_ab.py`、`run_sampling_ab.py`、`run_continue_*.py`、`run_fold_cache.py`、`run_heartbeat_live.py` | 预填充、缓存、续写、心跳 | 不评语义 |
| `kiln/benchmarks/generation-fidelity/` | 图像/视频的主体、数量、空间、动作、风格 | 不是文本长上下文 |
| `kiln/benchmarks/video/`、`kiln/scripts/wan_bench.py` | 视频运行时 | 同上 |
| `kiln/backend/tests/test_long_conversation.py` | API 能否存下 50 轮（100 条消息） | 存储，不是模型记忆 |
| `kiln/backend/app/services/dialogue_context.py` 及对应测试 | 超预算时把旧轮折成摘要卡 | 产品压缩行为。这套题不测压缩器，只测一份完整材料里的作答 |

因此现有数字不能回答：事实在开头、中段、结尾会不会丢；近形名字会不会张冠李戴；日期和金额会不会取到邻项；跨段状态推得对不对；长代码里能不能点名函数；对话记录里早期事实会不会被后文带偏；乱序步骤会不会按书写顺序执行。

## 题库

材料是窑场虚构记录，不是用户数据。位置类把唯一事实放在全文约 2%（开头）、50%（中段）或 99%（结尾），其余是可重复的无关日常段。无关段不含该题的标准答案。

| id | 类别 | 语言 | 规则 | 标准答案 | 在考什么 |
|---|---|---|---|---|---|
| lc-en-start-01 | fact_near_start | en | exact | `INV-7K2-Q9` | 开头的备用逆变器序列号 |
| lc-zh-start-02 | fact_near_start | zh | exact | `釉-丙午-318` | 开头的备用釉料批号 |
| lc-en-end-01 | fact_near_end | en | exact | `41-08-73` | 文末夜班柜密码 |
| lc-zh-end-02 | fact_near_end | zh | exact | `验-庚-9041` | 封卷里的末班验收单号 |
| lc-en-mid-01 | fact_near_middle | en | exact | `146.520` | 中段备用无线电频道 |
| lc-zh-mid-02 | fact_near_middle | zh | exact | `18.6 米` | 中段备用泵扬程 |
| lc-en-distract-01 | distractor_entities | en | exact | `Q-17` | 码头文员 Lin Wei。干扰项：Lin Weiwei `Q-71`、Lynn Wei `Q-11`、Linway Chen `Q-70`。作废纸条会把人和工号对调 |
| lc-zh-distract-02 | distractor_entities | zh | exact | `林薇 K-204` | 甲窑窑温记录员。干扰项：林微 `K-240`、林维 `K-402`、林蔚 `K-420` |
| lc-en-num-01 | exact_date_number | en | contains_all | `2024-11-07` 与 `18450` | 仍生效的是附录 C。旁边有 `2023-11-07`、`2024-11-17`、`1845`、`184500`、`14850` |
| lc-zh-num-02 | exact_date_number | zh | exact | `2023-04-18\|2764\|36.5` | 已结算的第三批。干扰：`276.4`、`27640`、`2674`、另一笔同样的 `36.5`、差一天或差一个月的日期 |
| lc-en-cross-01 | cross_paragraph | en | contains_all | `remains at dock 3` 与 `HOLD` | 红箱分到 3 号坞，09:10 已标 HOLD，中午转移不及它。绿箱 13:00 才标 HOLD，蓝箱本来在 7 号坞 |
| lc-zh-cross-02 | cross_paragraph | zh | contains_all | `留在维修台` 与 `在修` | C-9 在 11:20 标成在修，15:00 转移留不住它。C-5 是 16:00 才标的，所以晚间在乙组柜。晚间清单没有再写 C-9 |
| lc-en-code-01 | code_function_lookup | en | exact | `fold_batch_tag` | 去空格、加 `kiln:`、小写十六进制。近形：`fold_batch`、`batch_tag`、`fold_tag`、`tag_batch_fold`、`hex_batch`、`fold_batch_upper`。定义在源文件约 40% 处 |
| lc-zh-code-02 | code_function_lookup | zh | exact | `clamp_soak` | 保温分钟限制在 0 到 240 并返回整数。近形：`bound_soak` 返回小数，`clamp_soak_hours` 是小时 0 到 24，`clamp_soak_wide` 是 0 到 480 |
| lc-en-dialog-01 | multi_turn_memory | en | exact | `Moss\|7` | 记录里的用户自己的猫。邻居的猫是 Mossy，3 岁 |
| lc-zh-dialog-02 | multi_turn_memory | zh | exact | `周晚\|3月9日` | 用户的妹妹。同事是周晚晴，生日 9月3日 |
| lc-en-order-01 | ordered_event_chain | en | ordered | `E1` `E2` `E3` `E4` | 纸面顺序是 E3、E1、E4、E2。时钟是 08:05、08:50、09:40、11:15 |
| lc-zh-order-02 | ordered_event_chain | zh | ordered | `记录窑号` `称釉` `封窑` `取样` | 纸面是 3 封窑、1 记录窑号、4 取样、2 称釉。要按编号而不是按书写顺序 |

两条顺序题里，正确顺序不是材料的子序列。把材料整段抄进答案，过不了 `ordered`。

## 评分规则

归一化：NFKC、去掉零宽字符、把连续空白收成一个空格、去掉首尾空白。大小写敏感，所以 `inv-7k2-q9` 不算对。全角数字会经 NFKC 收成半角。

- `exact`：归一化后整段相等。多一个字就错，用来挡住回抄。
- `contains_all`：`gold` 是字符串列表，每段都要出现，顺序不限。
- `ordered`：列表必须按顺序出现（子序列），中间可以有别的字。

`contains_all` 和 `ordered` 使用边界，避免短答案命中更长的词：

- ASCII 字母数字不能从更长的词中间切出来。`18450` 对不上 `184500`，`Moss` 对不上 `Mossy`，`Q-17` 对不上 `Q-170`，`E1` 对不上 `E10`。
- 汉字同样不能从更长的词里切。`周晚` 对不上 `周晚晴`。

局限要留在记录里。`contains_all` 只检查必要片段在不在，否定句里如果仍带着这些片段会误过。`ordered` 只要后面又按对的顺序说了一遍也会过。位置、工号、函数名、对话记忆用 `exact`，就是为了避开这个洞。

缺预测算错。未知 id 打到 stderr，不进分母。用例或预测 id 重复、规则不在三种之内，退出码 2。有任何错题，退出码 1。全对才是 0。

## 扩到约 2 万 token

现在每条是审阅尺寸，不是 2 万 token。每条的 `generator_note` 写了怎么加长。共同约束：

- 只重复无关日常段，或在代码题里成对插入不改变语义的 `note_*`。
- 开头题的针保持第一段，结尾题的针保持最后一段，中段题两侧等量加长，代码题的目标函数留在源文件中部。
- 不要把 `gold`、近形人名、近形编号、日期或同语义函数写进填充。
- 不要为了填长度去调用模型。

这次没有生成 2 万 token 版本。

## 试跑

假预测按标准答案填对，故意把 `lc-en-distract-01` 写成 `Q-71`。那是起重机操作员 Lin Weiwei 的工号，不是码头文员 Lin Wei 的 `Q-17`。用来证明干扰项失败能被打出来。

```bash
python3 /Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/scripts/score_longctx.py \
  --cases /Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/benchmarks/longctx/cases.jsonl \
  --preds /Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/raw/A9/predictions.jsonl
```

退出码 1。标准输出：

```text
category                    n  correct accuracy
code_function_lookup        2        2    1.000
cross_paragraph             2        2    1.000
distractor_entities         2        1    0.500
exact_date_number           2        2    1.000
fact_near_end               2        2    1.000
fact_near_middle            2        2    1.000
fact_near_start             2        2    1.000
multi_turn_memory           2        2    1.000
ordered_event_chain         2        2    1.000
OVERALL                    18       17    0.944
FAIL	lc-en-distract-01	distractor_entities	exact	got=Q-71	gold=Q-17
```

`distractor_entities` 2 题对 1，总准确率 17/18。其余类别在这组假预测上是 1.000。stderr 无输出。

## 这次没有做

- 没有对在线模型出题，也没有测 TTFT 或 tok/s。编排允许基准之前不要用这套题打服务。
- 没有测对话压缩、截断或 2 万 token 预填充会不会把针裁掉。
- 没有把题库接进 pytest。评分器可以以后当回归门，但现在的退出码 1 只是故意错题。
