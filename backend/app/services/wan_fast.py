"""Wan 1.3B generate with T5 kept in bfloat16 (skip 11GB fp32 upcast)."""
from __future__ import annotations

import os
from pathlib import Path

import mlx.core as mx


def _load_t5_bf16(model_path, config):
    from mlx_video.models.wan_2.text_encoder import T5Encoder

    encoder = T5Encoder(
        vocab_size=config.t5_vocab_size,
        dim=config.t5_dim,
        dim_attn=config.t5_dim_attn,
        dim_ffn=config.t5_dim_ffn,
        num_heads=config.t5_num_heads,
        num_layers=config.t5_num_layers,
        num_buckets=config.t5_num_buckets,
        shared_pos=False,
    )
    weights = mx.load(str(model_path))
    encoder.load_weights(list(weights.items()))
    mx.eval(encoder.parameters())
    return encoder


def install_t5_bf16_patch() -> None:
    import mlx_video.models.wan_2.generate as g
    import mlx_video.models.wan_2.utils as u

    u.load_t5_encoder = _load_t5_bf16
    g.load_t5_encoder = _load_t5_bf16


def generate(
    *,
    model_dir: str,
    prompt: str,
    output_path: str,
    tokenizer_dir: str | None = None,
    width: int = 832,
    height: int = 480,
    num_frames: int = 17,
    steps: int = 10,
    guide_scale: float = 5.0,
    seed: int = 42,
    tiling: str = "auto",
    negative_prompt: str | None = None,
    teacache: float = 0.05,
    teacache_ret: bool = False,
) -> None:
    if tokenizer_dir:
        os.environ["WAN_T5_TOKENIZER"] = tokenizer_dir
    install_t5_bf16_patch()
    tea = None
    no_compile = False
    if teacache and teacache > 0:
        from app.services.wan_teacache import install_teacache

        tea = install_teacache(thresh=teacache, steps=steps, use_ret=teacache_ret)
        no_compile = True
    from mlx_video.models.wan_2.generate import generate_video

    generate_video(
        model_dir=model_dir,
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        num_frames=num_frames,
        steps=steps,
        guide_scale=guide_scale,
        seed=seed,
        output_path=output_path,
        tiling=tiling,
        no_compile=no_compile,
    )
    if tea is not None:
        print("TEACACHE", tea.as_dict(), flush=True)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--model-dir", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--output-path", required=True)
    p.add_argument("--tokenizer-dir", default="")
    p.add_argument("--width", type=int, default=832)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--num-frames", type=int, default=17)
    p.add_argument("--steps", type=int, default=10)
    p.add_argument("--guide-scale", type=float, default=5.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--tiling", default="auto")
    p.add_argument("--teacache", type=float, default=float(os.environ.get("VIDEO_TEACACHE_THRESHOLD", "0.05")))
    p.add_argument("--teacache-ret", action="store_true")
    a = p.parse_args()
    generate(
        model_dir=a.model_dir,
        prompt=a.prompt,
        output_path=a.output_path,
        tokenizer_dir=a.tokenizer_dir or None,
        width=a.width,
        height=a.height,
        num_frames=a.num_frames,
        steps=a.steps,
        guide_scale=a.guide_scale,
        seed=a.seed,
        tiling=a.tiling,
        teacache=a.teacache,
        teacache_ret=a.teacache_ret,
    )
