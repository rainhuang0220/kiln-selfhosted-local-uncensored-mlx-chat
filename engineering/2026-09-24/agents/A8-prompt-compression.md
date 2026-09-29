# A8 提示压缩

2026-09-24。只读 Kiln 源码，没有改它，没有 pip install，没有下载模型，没有打生成服务。KV 压缩不在这里设计，归 A7。

上游仓库说法里的压缩倍数都不是本机测出来的，下文不把它们当成 Kiln 的结果。

## 结论

本机三个虚拟环境都没有 `llmlingua` / `llmlingua-2`。LLMLingua-2 的小模型要显式传入 `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`；构造函数默认并不是它。

Kiln 现在的生产路径已经有两截有损处理：对话折轮（`build_dialogue_context`）和最新用户消息的抽块（`pack_user_message`）。它们都不记录源字符偏移，也不在丢数字、否定、编号顺序、代码标识符时拒绝结果。`compress_messages` 只被测试调用，不在出站路径上。

建议按下面的顺序用，前一层够用就停：

1. 精确上下文：库里的用户原文不动；出站前缀按模型 + tokenizer + 模板 + 渲染字节哈希对齐，能放进预算就整段原文送出。
2. 超预算再分块检索，块必须带消息 id 和源偏移，按源顺序拼回，不按分数重排。
3. 还超预算才允许有损压缩，并且先过回归。数字、日期、否定、代码标识符、编号顺序任一失败，就退回整段丢弃，不要交一份 token 沙拉。
4. 不做 KV 压缩。

中文对话和代码不能共用一个删除策略。压缩器自己的耗时和前缀缓存失效必须算进端到端，不能只看上游返回的 token ratio。

## 本机安装

三个环境都是 CPython 3.12.12。用各环境的 `importlib.metadata` 按名字过滤 `lingua` / `compress` / `selective` / `prompt`，结果是 `NONE`。`importlib.util.find_spec("llmlingua")` 都是 false。没有执行 pip install。

| 环境 | Python | pip 可执行文件 | 发行包数量 | llmlingua |
| --- | --- | --- | --- | --- |
| `/Users/rainhuang/Desktop/models/.media-venv` | 3.12.12 | 有 | 94 | 未安装 |
| `/Users/rainhuang/Desktop/models/.mtplx-venv` | 3.12.12 | 有 | 45 | 未安装 |
| `/Users/rainhuang/Desktop/models/kiln/.venv` | 3.12.12（uv 0.10.0） | 无 | 63 | 未安装 |

原始记录：`/Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/raw/A8/venv-scan.txt`。

## LLMLingua-2（仓库，不是本机实测）

核对的是 `microsoft/LLMLingua` 的 `main`。当时 HEAD 是 `5a4c78ae18ab17a98cf997e8259354e546081d64`（2026-09-10，只 pin 了 GitHub Actions SHA）。`llmlingua/version.py` 写的是 `0.2.2`。这是树上的版本号，不是本机已安装版本。

安装入口是 README 写的 `pip install llmlingua`，代码入口是 `from llmlingua import PromptCompressor`。同一个包覆盖 LLMLingua、LongLLMLingua 和 LLMLingua-2，没有单独的 `llmlingua-2` 发行包。

LLMLingua-2 用的是 token 分类编码器，不是困惑度小模型。README 和 `DOCUMENT.md`、`Transparency_FAQ.md` 把小模型写成：

`microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`

同时 `use_llmlingua2=True`。大模型名字是 `microsoft/llmlingua-2-xlm-roberta-large-meetingbank`。模型 id 里的 MeetingBank 是会议转写语料，不是代码，也不是 Kiln 的中文对话。

这不是构造函数的默认值。`prompt_compressor.py` 里 `model_name` 默认是 `NousResearch/Llama-2-7b-hf`，`use_llmlingua2` 默认 `False`，`device_map` 默认 `cuda`。只开 `use_llmlingua2=True` 而不改名字，加载的仍是 Llama-2-7B。`prompt_compressor.py` 里搜不到 `bert-base-multilingual` 这个字符串，小模型名字只出现在文档示例里。文档字符串里的示例用的是 xlm-roberta-large，不是 small。

`init_llmlingua2` 把 `max_seq_len` 设为 512，分块时还要留 2 个位置给 CLS/SEP。长提示要多次前向。文档里的 `chunk_end_tokens` 默认是 `[".", "\n"]`，不包含中文句号。

数字没有被默认保住。`force_reserve_digit` 默认 `False`；只有显式打开时，含 `0-9` 的 token 才会被抬到保留概率。它不保护代码标识符。README 自己的快速开始样例把算术题压成了 `1 boxes x00`、`12 * 300ters`、`5 *5`。结构化样例把 `11, three, 14, 16 and 28` 收成 `are11,,116 28`。这就是仓库展示出来的数字弱点，不是这里重新跑出来的。代码同样是按词丢 token，没有标识符白名单。`examples/Code.ipynb` 是另一条代码补全演示；它里面的倍数和分数变化这里不引用、不当成结果。

端到端成本必须另算。压缩接口返回的是 `origin_tokens`、`compressed_tokens`、`ratio`，外加一个 `saving` 字符串（样例里是 GPT-4 美元）。这里面没有压缩器加载、没有 512 窗口的多次前向，也没有 Kiln 前缀缓存被改写之后的 prefill。短 prompt 如果把已经缓存的前缀打乱，墙钟时间可以比不压缩更差。本机没有量过这条差。

摘录：`/Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/raw/A8/llmlingua-facts.txt`。

## 现在的出站路径

`ChatService._build_payload`（`backend/app/services/chat.py`）用 `settings.practical_prompt_budget`。`config.py` 里的默认值是 32768。用户原文经 `_insert_message` 写入 `messages.content`。打包和折轮只改当次 `sent` 和 snapshot，不从这段代码写回消息表。

两截有损处理：

- `build_dialogue_context`：放不下就按轮折进 `<dialogue_state>` 和 `<history_summary>`，至少留最近 4 轮原文。状态抽取是一小撮标签正则（地点、约定、事件、偏好、目标、场景、参与者，外加「在/去了/来到」「喜欢/不喜欢/不要/想要」「还没」）。摘要按句截断，总长超过 1200 就只留尾部。折出来的块被插成一条 `id=dialogue-context` 的 user 消息，紧挨在 system 后面。前缀因此每次折轮都变。
- `pack_user_message`：只处理最新一条用户消息。`split_chunks` 约 1600 字、重叠约 80 字，返回纯字符串，没有 start/end。超长单行按字切。`pack_document` 留首尾块，中间按词面重叠打分，输出时按块下标排序，缺口写 `[... omitted ...]`。重叠行会在下一块里再出现一次。

`compress_messages` / `extractive_summary`（每条截 160 字）不在这条路径上。

渲染已经是模型自己的 tokenizer 和 `chat_template`（`tokens.py` 的 `apply_chat_template`），不是手写 ChatML。`enable_thinking` 会改变渲染字节。架构说明要求每次把完整 `messages[]` 发给 mlx，靠前缀字节命中缓存。记忆用 `<memory>` 贴在最新用户句旁边，不写进 `role=system`。Continue 另有一条约束：mlx-lm 0.31.3 在完全相同的 prompt-cache 命中上会空掉 `insert_segments` 并弄死生成线程（`continuation.py`）。精确层不要去改那条 Continue 逻辑。

## 四层

### 1. 精确上下文

真相是 `chat.db` 里的原文。压缩、折轮、抽块都不得回写 `messages.content`。

装得进 `practical_prompt_budget` 时，出站消息就是原文加现有的 system / memory 围栏，不做折轮，不插入 `dialogue-context`。同一模型、同一模板开关下，已发送过的前缀字节保持不变，新轮只追加在后面。

前缀缓存键用四段，缺一不可：

- 模型身份：活跃模型路径或修订，不是 mlx 请求里那个固定的 `"default_model"` 字符串。
- tokenizer 身份：`tokenizer.json` 与 `tokenizer_config.json` 的哈希。
- 模板身份：`chat_template.jinja` 的哈希，再加上会改变渲染的开关（`enable_thinking`、`add_generation_prompt`、`continue_final_message`）。
- 内容身份：上述三者渲染出的前缀字符串的 sha256。

键相同才可以指望 mlx 吃到同一段前缀。摘要或抽块只要改了前缀中间的字节，这一键就失效，失效要记进第 3 层的端到端账，而不是当成免费缩短。

可变的折轮块不要放进 `role=system`，也不要再插到 system 和旧原文之间。真要附带状态，放在稳定原文前缀之后。Continue 的「故意少一个 token」仍然只属于续写路径。

### 2. 分块检索，带源偏移

只在精确上下文放不下时启用。对象是超长的单条用户文本，以及第 1 层保不住的旧轮。最近若干轮保持原文，沿用现在「至少 4 轮」的下限，不要先压缩它们。

块是指向原文的区间，不是另一份改写过的字符串：

- `message_id`
- `start`、`end`：该条 `content` 上的半开字符偏移
- 文本必须等于 `content[start:end]`

重叠只许用来打分，不许写进出站 prompt，避免同一行出现两次。选中哪些块可以继续用现在的词面重叠（`_terms` / `_score`）。拼回时按消息顺序和 `start` 排，不按分数排。缺口保留显式省略标记，并带上被省略区间的偏移，而不是只写 `[... omitted ...]`。

代码和编号步骤按行切。一行本身超过预算时，整行留下或整行丢掉，不在标识符中间切开。现在的 `split_chunks` 会把超长行切成 1600 字，这一刀应该停用在代码上。

这一层仍然是抽取，不是释义。被丢掉的区间在库里还在，UI 可以按偏移跳回。

### 3. 提示压缩，带回归

只压缩第 2 层之后仍然超预算的、非代码、非最近轮的区间。候选可以是整句删除，以后也可以是外部压缩器。本任务不接入 LLMLingua，也不下载那个 BERT。

无论用哪一种，交出模型之前都对「被替换的原文」和「压缩结果」跑回归。失败就拒绝这份压缩，改回第 2 层的整段丢弃。不要把失败的压缩当成摘要留下。

设计上要卡住的东西：

| 项 | 要求 | 这次的脚本 |
| --- | --- | --- |
| 事实 | 钉住的事实（金额、专名、`DialogueState` 里的 value、用户原文里的约定）必须仍是原文子串，或者该区间被明确标成省略 | 不做。没有事实蕴含判断 |
| 数字 | 原文里的数字多重集不能变少 | 做了 |
| 日期 | 数字日期不能丢 | 只覆盖 `\d{4}-\d{2}-\d{2}`、`\d{4}/\d{2}/\d{2}` 以及散落的数字。`2026年9月24日` 会留下 `2026`/`9`/`24`，`九月` 这种不覆盖 |
| 代码标识符 | snake_case、简单驼峰、反引号名字不能丢 | 做了。不认纯大写缩写，不认普通英文单词 |
| 否定 | `不` / `没` / `not` / `never` 不能变少 | 做了。`cannot`、`别`、`未`、`n't` 不在表内 |
| 顺序 | 编号步骤的相对顺序不能变；无编号文档也不许按相关度重排 | 脚本只查编号行。无编号顺序是这条设计规则，不是脚本规则 |

现有折轮没有这道门。`_fold_summary` 超长时留尾部，切点可以落在数字或「不」中间；`merge_state` 的正则也留不住自由文本里的否定。在这道门落地之前，折轮结果不能当成保真。

端到端只记这些，不记上游论文倍数：

- 压缩器墙钟。没用压缩器就是 0。若以后用 LLMLingua-2，还要加上模型加载和每大约 510 token 一次的分类前向。
- 压缩前 token、压缩后 token。这只是体积，不是时延。
- 前缀缓存命中了多少 token。消息表已有 `cached_tokens`，但本次没有打生成服务，没有新样本。
- 未命中前缀的 prefill 与解码。

对照物是「同一条请求、不压缩、前缀能对上」的墙钟，不是 README 里的 `ratio` 或 `saving`。

### 4. 不做 KV 压缩

A7 负责 KV。LLMLingua README 里的 KV-cache 压缩、SCBench、RetrievalAttention、MInference 都不在本层。这里只决定送出的提示字符串，不改缓存张量、不改量化、不做 offload。

## 中文和代码分策

不能共用一个压缩率，也不能共用 LLMLingua 的默认分块。

中文对话：否定经常是一个字，「不要」变成「要」就是反义。策略是整句保留或整句按偏移删除，不按 token 删字。句界用 `。！？` 和换行，不用默认的 `[".", "\n"]`。最近轮次保持原文。MeetingBank 上的多语 BERT 只说明词表里有中文，不说明这条对话上能用。这里没有中文压缩样本。

代码和操作步骤：标识符、数字、顺序就是内容。禁止 token 级压缩，也不使用 LongLLMLingua 的 `reorder_context=sort`。`force_reserve_digit` 即使打开也只照顾数字，默认还是关的，覆盖不了 `parse_user_id`。策略是围栏代码和像代码的行整段抽取、按源偏移省略，留下来的行与原文逐字相同。

两条都先过同一套回归。中文失败多半落在「不/没」和句界；代码失败多半落在标识符、数字和编号顺序。失败的处理一样：退回整段丢弃，不接受有损字符串。

## 离线回归脚本

路径：`/Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/scripts/compress_regression_checks.py`。

只依赖标准库（`re`、`sys`、`collections`）。四个内置用例覆盖：保真缩短应无旗标、丢掉 `42` 和 `2026-09-24`、丢掉 `not`/`never`/`不`/`没` 并调换编号行、丢掉 `parse_user_id` 和 `` `ChatService` `` 但留着 `user_id`。`__main__` 打印每例 `PASS`/`FAIL`，最后再打印总的 `PASS` 或 `FAIL`。

命令：

```text
python3 -S /Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/scripts/compress_regression_checks.py
```

stdout（exit 0）：

```text
PASS clean_keeps_constraints
PASS drops_number_and_date
PASS drops_negation_and_reorders
PASS drops_code_identifier
PASS
```

同一解释器用 `python3 -S` 加载该文件且不跑 `__main__`，`sys.modules` 里没有 `torch`、`transformers`、`llmlingua`、`mlx`、`mlx_lm`、`tokenizers`。日志：`/Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/raw/A8/compress_regression_checks.out.txt`。

脚本没有接到 `build_dialogue_context` 或 `pack_user_message` 上。那是源码改动，这次不做。

## 这次没有测的

没有压缩比。没有时延。没有把 LLMLingua-2 的小模型或 Llama-2-7B 拉到本地。没有请求 mlx 或 Kiln 的生成接口。README 和 Code notebook 里的倍数都留在上游，不进入 Kiln 的账。
