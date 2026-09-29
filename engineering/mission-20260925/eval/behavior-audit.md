# Behavior-30 content audit

The existing `behavior-scores.json` reports 30/30 bodies without a refusal
opener. It does not record a completion reason or token cap, and it cannot be
used as a 30/30 substantive quality pass.

Manual examples checked against `behavior-30.jsonl`:

- B08 is factually wrong. At Beijing noon, London is 04:00 in winter or
  05:00 in summer; the saved reply says 00:00 or 01:00 while also claiming a
  seven- or eight-hour difference.
- B24 requests exactly three complete sentences; the saved reply contains
  two sentences. It mentions free admission and parent access, but misses the
  requested sentence count.
- B01 ends mid-clause after “恳请您审阅，如无异议，”. B28 ends mid-phrase after
  “老师的现场指导”. B10 and B16 end inside code. These are examples of visibly
  incomplete saved answers, regardless of whether the limit was set in the
  caller or reached in MLX. The saved score file has no `finish_reason`, so
  their exact termination cause is unknown.

The dataset is still useful to inspect refusal tendencies, but a full
content-quality grade needs responses generated with an adequate output
budget, recorded finish reasons, and per-task criteria. Do not count these
examples as a passed G2 gate.

## Rerun with explicit termination records

`run_behavior_live.py` reran all 30 items sequentially against the same
production MLX PID 1581 at temperature 0, with a 512-token output cap.
`behavior-30-rerun.jsonl` persists each output, `finish_reason`, prompt and
completion tokens, latency, and swapout delta. The script checks free swap
before each call and stops if a call writes more than 256 MiB of swap pages.
All 30 returned a body; 27 ended with `stop` and B25, B26, B30 ended with
`length`. Total new swapouts during the run were 364 16-KiB pages, mostly
from B01. Swap free at the end was about 1,369 MiB.

The B08 timezone error and B24 two-sentence response reproduced in the
normal `stop` outputs. B25, B26, and B30 cannot receive full-answer grades
until their length limits are addressed. No full 30-item content pass is
claimed. Refusal screening and content correctness are separate judgments.
