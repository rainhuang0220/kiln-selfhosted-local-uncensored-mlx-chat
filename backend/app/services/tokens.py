from __future__ import annotations

from pathlib import Path
from typing import Any


class TokenEstimator:
    def __init__(self, model_path: str, trust_remote_code: bool = False):
        self.model_path = Path(model_path)
        self.trust_remote_code = trust_remote_code
        tok_file = self.model_path / "tokenizer.json"
        self._tok = None
        self._hf = None
        self._load_error: str | None = None
        if tok_file.exists():
            try:
                from tokenizers import Tokenizer

                self._tok = Tokenizer.from_file(str(tok_file))
            except Exception as exc:  # noqa: BLE001
                self._load_error = str(exc)
        else:
            self._load_error = f"missing {tok_file}"
    def _hf_tokenizer(self):
        if self._hf is not None:
            return self._hf
        if not (
            (self.model_path / "tokenizer_config.json").exists()
            or (self.model_path / "chat_template.jinja").exists()
        ):
            return None
        try:
            from transformers import AutoTokenizer

            self._hf = AutoTokenizer.from_pretrained(
                str(self.model_path),
                trust_remote_code=self.trust_remote_code,
            )
        except Exception as exc:  # noqa: BLE001
            self._load_error = str(exc)
            return None
        return self._hf

    @property
    def method(self) -> str:
        if self._hf is not None or (self.model_path / "chat_template.jinja").exists():
            return "hf_chat_template"
        if self._tok is not None:
            return "hf_tokenizer"
        return "chars_div_4"

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        if self._tok is not None:
            return len(self._tok.encode(text).ids)
        if self._hf is not None:
            return len(self._hf.encode(text, add_special_tokens=False))
        return max(1, len(text.encode("utf-8")) // 4)

    def apply_chat_template(
        self,
        messages: list[dict],
        *,
        assistant_prefix: str | None = None,
        add_generation_prompt: bool = True,
        continue_final_message: bool = False,
        enable_thinking: bool = False,
    ) -> str:
        """Render with the model tokenizer. No handwritten ChatML."""
        msgs: list[dict[str, Any]] = [dict(m) for m in messages]
        if assistant_prefix is not None:
            msgs.append({"role": "assistant", "content": assistant_prefix})
            continue_final_message = True
        if continue_final_message:
            add_generation_prompt = False
        hf = self._hf_tokenizer()
        if hf is None:
            raise RuntimeError(
                "tokenizer.apply_chat_template requires the model chat template "
                f"at {self.model_path}: {self._load_error}"
            )
        return hf.apply_chat_template(
            msgs,
            tokenize=False,
            continue_final_message=continue_final_message,
            add_generation_prompt=add_generation_prompt,
            enable_thinking=enable_thinking,
        )

    def continuation_completion_prompt(
        self,
        messages: list[dict],
        *,
        enable_thinking: bool = False,
        used_prompts: list[str] | None = None,
    ) -> tuple[str, str]:
        from app.services.continuation import shorten_until_unused

        native = self.apply_chat_template(
            messages,
            continue_final_message=True,
            add_generation_prompt=False,
            enable_thinking=enable_thinking,
        )
        hf = self._hf_tokenizer()
        if hf is None:
            raise RuntimeError(
                "tokenizer.apply_chat_template requires the model chat template "
                f"at {self.model_path}: {self._load_error}"
            )
        return shorten_until_unused(
            native,
            encode=lambda text: hf.encode(text, add_special_tokens=False),
            decode=lambda ids: hf.decode(ids, skip_special_tokens=False),
            used=used_prompts,
        )

    def mid_think_completion_prompt(
        self,
        messages: list[dict],
        reasoning: str,
        *,
        used_prompts: list[str] | None = None,
    ) -> tuple[str, str]:
        from app.services.continuation import shorten_until_unused

        prefix = self.apply_chat_template(
            messages,
            add_generation_prompt=True,
            enable_thinking=True,
        )
        native = prefix + (reasoning or "")
        hf = self._hf_tokenizer()
        if hf is None:
            raise RuntimeError(
                "tokenizer.apply_chat_template requires the model chat template "
                f"at {self.model_path}: {self._load_error}"
            )
        return shorten_until_unused(
            native,
            encode=lambda text: hf.encode(text, add_special_tokens=False),
            decode=lambda ids: hf.decode(ids, skip_special_tokens=False),
            used=used_prompts,
        )

    def count_messages(
        self,
        messages: list[dict],
        *,
        enable_thinking: bool = False,
    ) -> int:
        try:
            return self.count_text(
                self.apply_chat_template(messages, enable_thinking=enable_thinking)
            )
        except RuntimeError:
            return sum(
                self.count_text((m.get("content") or "") + (m.get("reasoning") or ""))
                for m in messages
            ) or 1
