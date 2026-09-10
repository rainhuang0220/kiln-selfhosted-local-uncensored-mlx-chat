# Generation fidelity bench

Separates **refusal** from **prompt adherence**.

This directory commits only benign prompts, the score schema, and a runner.
Do not commit private user prompts, private outputs, or generated media.

## Refusal vs adherence

- Refusal: the model declines, a hidden filter rewrites the prompt, or the runtime strips content.
- Adherence: the model generates, but subject, count, space, action, or style is wrong.

A willing wrong answer is an adherence miss, not proof of censorship.

## Prompts

`prompts.json` is a safe compositional set (color, count, left/right, camera, lighting, style).

## Scoring

Use `schema.json`. Score 0/1 per axis, then `overall` as the mean.

```text
prompt_preservation
subject
attributes
count
spatial
action
style
overall
```

Write filled cards under `runs/` (gitignored).

## Run

```bash
python3 benchmarks/generation-fidelity/run.py --list
```

The runner only prints the public prompt set. Generation is manual or via Kiln Raw/Enhanced with a fixed seed so later model swaps are comparable.

## Visual A/B

`visual_ab.json` is a larger benign set (Chinese, English, mixed, multi-constraint). Outputs go to `runs/` and must not be committed.

```bash
python3 benchmarks/generation-fidelity/run_visual_ab.py --kind image --limit 4
python3 benchmarks/generation-fidelity/run_visual_ab.py --kind image --ids img-action-zh,img-spatial-zh,img-count-en,img-camera-zh
python3 benchmarks/generation-fidelity/run_visual_ab.py --kind video --limit 2
```

Image modes are `raw`, `enhanced`, and experimental `translate_enhance` (Chinese → English → enhance). Do not make Translate+Enhance the default unless visual A/B shows a clear adherence win.

Score constraint satisfaction, not prettiness. Open `runs/contact-sheet.html` for side-by-side Raw vs Enhanced.

Filled score cards stay out of git (`data/private-evals/`, `runs/`). Aggregate with:

```bash
python3 benchmarks/generation-fidelity/summarize_scores.py path/to/scores.json
```

`*.png` / `*.mp4` / `runs/` are gitignored. Do not commit generated media or private prompts.
