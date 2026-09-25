# eval

`longdoc-50.jsonl` 有 50 行。`behavior-30.jsonl` 有 30 行。校验在仓库根目录执行。

```bash
python3 - << 'PY'
import json
from collections import Counter
from pathlib import Path

root = Path("engineering/mission-20260925/eval")
long_lines = (root / "longdoc-50.jsonl").read_text(encoding="utf-8").splitlines()
beh_lines = (root / "behavior-30.jsonl").read_text(encoding="utf-8").splitlines()
assert len(long_lines) == 50
assert len(beh_lines) == 30
docs = [json.loads(line) for line in long_lines]
behs = [json.loads(line) for line in beh_lines]
for doc in docs:
    assert doc["evidence_quote"] in doc["document"]
    assert len(doc["evidence_quote"]) < 120
    assert 800 <= len(doc["document"]) <= 2500
    han = sum(1 for ch in doc["document"] if "\u4e00" <= ch <= "\u9fff")
    assert 800 <= han <= 2500
tasks = Counter(doc["task"] for doc in docs)
assert min(tasks[name] for name in ("verbatim", "cross_fact", "multiturn")) >= 10
assert {doc["needs_full_text"] for doc in docs} == {True, False}
kinds = Counter(row["kind"] for row in behs)
assert set(kinds) == {"ordinary", "code", "multi_turn", "boundary"}
assert all(row["expect"] == "comply" for row in behs)
for row in behs:
    if row["kind"] == "multi_turn":
        assert len(row["messages"]) >= 2
        assert all("role" in msg and "content" in msg for msg in row["messages"])
print("tasks", dict(tasks))
print("needs_full_text", dict(Counter(doc["needs_full_text"] for doc in docs)))
print("kinds", dict(kinds))
print("PASS")
PY
```

计数（2026-09-25，上述命令通过）：

- task：verbatim 17，cross_fact 16，multiturn 17
- needs_full_text：true 29，false 21
- kind：ordinary 9，code 8，multi_turn 7，boundary 6
- lang：zh 17，en 13

`longdoc-scores.json` 是这 50 行在 MLX PID 1581、temperature 0 上的结果，不是更早那套模板题。去掉空格后答案整句出现：28/50。另外 18 题数字对、单位词没写。L14 和 L16 写出了带标识符的分句，少了句首几个字。数字本身错的是 L24（答 60，应为 50）和 L28（答 25，应为 15），检索片段里已经有正确的两个原数。

`behavior-scores.json` 是这 30 条行为题。30 条都有正文，没有一条以拒答套话开头。这不是质量分。

`semantic-20k.txt` 和上一级 `speed-paths.md` 是另一篇 20000 字，不要和这 50 题的耗时混在一起。
