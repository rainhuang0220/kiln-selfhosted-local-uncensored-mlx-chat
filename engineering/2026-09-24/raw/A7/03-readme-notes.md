READMEs fetched via GitHub contents API. Not papers. SHAs are blob ids returned with the file.

## NVIDIA/kvpress README
- Repo: https://github.com/NVIDIA/kvpress
- Blob: bace06dab057a7610b3c7fb5a8185bee2478dee9
- Idea, from the README: training-free presses compress the KV cache, usually at prefill, via a `compression_ratio`. A press registers `forward_hook` on each attention layer (`press` as a context manager, or pipeline `kv-press-text-generation`).
- SnapKVPress one-liner in that README: average attention weight of the last queries.
- PyramidKVPress one-liner: pyramid-like cache sizes, more budget on lower layers, less on higher layers.
- Also documents HF `QuantizedCache` (quanto backend), default cache `DynamicCache`.
- FAQ models tested: LlamaForCausalLM, MistralForCausalLM, Phi3ForCausalLM, Qwen2ForCausalLM, Qwen3ForCausalLM, Gemma3ForCausalLM. No Qwen3.5 / hybrid linear attention.
- Plugs into: Hugging Face transformers (`from transformers import pipeline` / `AutoModelForCausalLM`), CUDA in the examples, optional flash-attn.

## FasterDecoding/SnapKV README
- Repo: https://github.com/FasterDecoding/SnapKV
- Blob: 1e505781926098398c104039aac9708a50385cb8
- Idea, from the README itself: an out-of-the-box KV cache compression method. The README does not write the scoring formula; it points at `snapkv/monkeypatch/snapkv_utils.py`.
- Plug-in: `from snapkv.monkeypatch.monkeypatch import replace_mistral` then `replace_mistral()`. Comments marked `[SnapKV]` in monkeypatches. Supported there: Llama family, Mistral, Mixtral. Tested `transformers==4.37.0` (requires `transformers>=4.36`) and `flash-attn==2.4.0`.

## Zefan-Cai/PyramidKV README
- Repo: https://github.com/Zefan-Cai/PyramidKV
- Blob: b6544df475a66e24ff54682bd5ccb21b36d05724
- The README title is now KVCache-Factory (renamed 2024-11-28). PyramidKV is one row: "layer-wise pyramidal cache budget".
- `--max_capacity_prompts` is the per-layer budget; PyramidKV redistributes that budget across layers.
- Plug-in: Hugging Face transformers pinned `transformers==4.44.2`, torch, optional flash-attn. Runners `run_longbench.py --method pyramidkv` (and needle / RULER). "Llama and Mistral attention paths are supported for the main compression methods." Monkeypatches are called version-sensitive. Default dtype float16. Not an MLX package.
