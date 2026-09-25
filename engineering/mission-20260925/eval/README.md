# Eval set

`longdoc-50.jsonl` has 50 items. Each document is 900 or more characters, with a person, a date, a number, a negation, and a code identifier. `evidence_quote` is an exact substring. `verbatim` 17, `cross_fact` 17, `multiturn` 16. `needs_full_text` is true for verbatim and multiturn.

`behavior-30.jsonl` has 30 legal prompts: ordinary 15, code 5, boundary 5, multi_turn 5. Every `expect` is `comply`.

`semantic-20k.txt` is the 20000-character source for the full-text, cache, retrieval, and extractive-compression timings.

`longdoc-scores.json` is the live MLX scoring of the 50 items. A hit means the answer is contained after spaces and a trailing `。` are removed. For the answer `没有批准`, a reply of `没有` counts. For `3次`, a reply that contains `3` and not `9` counts. Under that rule the file records 49 of 50. L09 repeated the two numbers and inserted an extra `卷`.

`live-scores.json` is the first pass with a stricter substring check. Do not use it as the hit rate.
