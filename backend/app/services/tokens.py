from __future__ import annotations

from pathlib import Path

from tokenizers import Tokenizer


class TokenEstimator:
    def __init__(self, model_path: str):
        self.model_path = Path(model_path)
        tok_file = self.model_path / "tokenizer.json"
        self._tok: Tokenizer | None = None
        self._load_error: str | None = None
        if tok_file.exists():
            try:
                self._tok = Tokenizer.from_file(str(tok_file))
            except Exception as exc:  # noqa: BLE001
                self._load_error = str(exc)
        else:
            self._load_error = f"missing {tok_file}"

    @property
    def method(self) -> str:
        return "hf_tokenizer" if self._tok is not None else "chars_div_4"

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        if self._tok is not None:
            return len(self._tok.encode(text).ids)
        return max(1, len(text.encode("utf-8")) // 4)

    def count_messages(self, messages: list[dict]) -> int:
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role") or "user"
            content = msg.get("content") or ""
            reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
            body = content
            if reasoning:
                body = f"<think>\n{reasoning}\n</think>\n\n{content}"
            parts.append(f"<|im_start|>{role}\n{body}<|im_end|>")
        parts.append("<|im_start|>assistant\n")
        return self.count_text("\n".join(parts))
