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
