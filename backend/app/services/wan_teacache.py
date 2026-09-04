"""Training-free TeaCache for Wan 1.3B (MLX)."""

Does not change checkpoints. Skip decision uses the Wan 1.3B polynomial
from ali-vilab/TeaCache; residual is applied in transformer hidden space.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import mlx.core as mx
import numpy as np

# TeaCache4Wan2.1 t2v-1.3B (no retention steps / with ret_steps).
COEFFS_1_3B = [
    2.39676752e03,
    -1.31110545e03,
    2.01331979e02,
    -8.29855975e00,
    1.37887774e-01,
]
COEFFS_1_3B_RET = [
    -5.21862437e04,
    9.23041404e03,
    -5.28275948e02,
    1.36987616e01,
    -4.99875664e-02,
]

LAST_STATE: "TeaState | None" = None


def _rel_l1(curr: mx.array, prev: mx.array) -> float:
    num = mx.mean(mx.abs(curr - prev))
    den = mx.mean(mx.abs(prev))
    mx.eval(num, den)
    n = float(num.item())
    d = float(den.item())
    return n / (d + 1e-9)


@dataclass
class TeaState:
    thresh: float
    steps: int
    use_ret: bool = False
    cnt: int = 0
    acc: float = 0.0
    skipped: int = 0
    computed: int = 0
    prev_e0: mx.array | None = field(default=None, repr=False)
    residual: mx.array | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        coeffs = COEFFS_1_3B_RET if self.use_ret else COEFFS_1_3B
        self.poly = np.poly1d(coeffs)
        self.ret_steps = 5 if self.use_ret else 1
        self.cutoff = self.steps

    def should_calc(self, e0: mx.array) -> bool:
        self.cnt += 1
        force = (
            self.prev_e0 is None
            or self.cnt <= self.ret_steps
            or self.cnt >= self.cutoff
            or self.residual is None
        )
        if force:
            self.prev_e0 = e0
            self.acc = 0.0
            self.computed += 1
            return True
        rel = _rel_l1(e0, self.prev_e0)
        self.prev_e0 = e0
        self.acc += float(self.poly(rel))
        if self.acc < self.thresh:
            self.skipped += 1
            return False
        self.acc = 0.0
        self.computed += 1
        return True

    def as_dict(self) -> dict:
        total = self.skipped + self.computed
        return {
            "thresh": self.thresh,
            "use_ret": self.use_ret,
            "skipped": self.skipped,
            "computed": self.computed,
            "skip_rate": round(self.skipped / total, 3) if total else 0.0,
        }


def _make_forward(state: TeaState):
    from mlx_video.models.wan_2.attention import _linear_dtype

    cores: dict[tuple, object] = {}

    def forward(
        self,
        x_list: list,
        t: mx.array,
        context: list | mx.array,
        seq_len: int,
        cross_kv_caches: list | None = None,
        y: list | None = None,
        rope_cos_sin: tuple | None = None,
    ) -> list:
        batch_size = len(x_list)
        all_same = batch_size > 1 and all(x_list[i] is x_list[0] for i in range(1, batch_size))
        if all_same and y is not None:
            all_same = all(y[i] is y[0] for i in range(1, len(y)))
        if y is not None:
            x_list = [mx.concatenate([u, v], axis=0) for u, v in zip(x_list, y)]

        if all_same:
            p, gs = self._patchify(x_list[0])
            grid_sizes = [gs] * batch_size
            seq_lens_list = [p.shape[1]] * batch_size
            if p.shape[1] < seq_len:
                p = mx.concatenate(
                    [p, mx.zeros((1, seq_len - p.shape[1], self.dim), dtype=p.dtype)],
                    axis=1,
                )
            x = mx.broadcast_to(p, (batch_size,) + p.shape[1:])
        else:
            patches = []
            grid_sizes = []
            seq_lens_list = []
            for vid in x_list:
                p, gs = self._patchify(vid)
                patches.append(p)
                grid_sizes.append(gs)
                seq_lens_list.append(p.shape[1])
            x = mx.concatenate(
                [
                    (
                        mx.concatenate(
                            [
                                p,
                                mx.zeros((1, seq_len - p.shape[1], self.dim), dtype=p.dtype),
                            ],
                            axis=1,
                        )
                        if p.shape[1] < seq_len
                        else p
                    )
                    for p in patches
                ],
                axis=0,
            )

        if t.ndim == 0:
            t = t[None]
        sinusoid = t[..., None].astype(mx.float32) * self._inv_freq
        sin_emb = mx.concatenate([mx.cos(sinusoid), mx.sin(sinusoid)], axis=-1)
        if t.ndim == 1:
            e = self.time_embedding_1(
                self.time_embedding_act(self.time_embedding_0(sin_emb))
            )
            e0 = self.time_projection(self.time_projection_act(e))
            e0 = e0.reshape(batch_size, 1, 6, self.dim)
        else:
            e = self.time_embedding_1(
                self.time_embedding_act(self.time_embedding_0(sin_emb))
            )
            e0 = self.time_projection(self.time_projection_act(e))
            e0 = e0.reshape(batch_size, -1, 6, self.dim)

        if isinstance(context, mx.array):
            context_batch = context
            if context_batch.shape[0] == 1 and batch_size > 1:
                context_batch = mx.broadcast_to(
                    context_batch, (batch_size,) + context_batch.shape[1:]
                )
        else:
            context_batch = self.embed_text(context)

        attn_mask = None
        w_dtype = _linear_dtype(self.patch_embedding_proj)
        if any(sl < seq_len for sl in seq_lens_list):
            attn_mask = mx.zeros((batch_size, 1, 1, seq_len), dtype=w_dtype)
            for i, sl in enumerate(seq_lens_list):
                attn_mask[i, :, :, sl:] = -1e9

        calc = state.should_calc(e0)
        ori_x = x
        if calc:
            key = (tuple(x.shape), tuple(e0.shape), seq_len, batch_size)
            core = cores.get(key)
            if core is None:
                blocks = self.blocks
                freqs = self.freqs
                kv_list = cross_kv_caches
                gs = grid_sizes
                sl = seq_lens_list
                mask = attn_mask
                rope = rope_cos_sin

                def compiled_fn(h, mod, ctx):
                    kwargs = dict(
                        e=mod,
                        seq_lens=sl,
                        grid_sizes=gs,
                        freqs=freqs,
                        context=ctx,
                        context_lens=None,
                        rope_cos_sin=rope,
                        attn_mask=mask,
                    )
                    for i, block in enumerate(blocks):
                        kv = kv_list[i] if kv_list is not None else None
                        h = block(h, cross_kv_cache=kv, **kwargs)
                    return h

                core = mx.compile(compiled_fn)
                cores[key] = core
            x = core(x, e0, context_batch)
            state.residual = x - ori_x
            mx.eval(state.residual)
        else:
            x = ori_x + state.residual

        x = self.head(x, e)
        outputs = self.unpatchify(x, grid_sizes)
        return [u.astype(mx.float32) for u in outputs]

    return forward


def install_teacache(thresh: float, steps: int, use_ret: bool = False) -> TeaState:
    global LAST_STATE
    from mlx_video.models.wan_2.wan_2 import WanModel

    state = TeaState(thresh=thresh, steps=steps, use_ret=use_ret)
    LAST_STATE = state
    WanModel.__call__ = _make_forward(state)
    return state
