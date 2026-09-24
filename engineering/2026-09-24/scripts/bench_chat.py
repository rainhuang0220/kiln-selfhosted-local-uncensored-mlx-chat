#!/usr/bin/env python3
"""Repeatable chat benchmark client for a running OpenAI-compatible MLX server.

Stdlib only. Does not import mlx, tokenizers, httpx, or requests, and does not
load weights or download anything. Refuses to run unless KILN_ALLOW_BENCH=1.
"""

from __future__ import annotations

import argparse
import codecs
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCHEMA = "kiln.bench_chat.v1"
ENGLISH_UNIT = "tok "
CJK_UNIT = "雨停之后旧书店的灯还亮着钥匙仍在抽屉第二层约定没有改期今晚八点送到门口"
CJK_SLOT = 32
HAN_HEX = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳"
READ_SIZE = 256
REQUEST_PIN = {
    "temperature": 1.0,
    "top_p": 0.95,
    "top_k": 20,
    "stream": True,
    "stream_options": {"include_usage": True},
    "chat_template_kwargs": {
        "enable_thinking": False,
        "reasoning_effort": "medium",
    },
}
# mlx-lm 0.31.3 APIHandler has no tokenize route. Kept empty on purpose.
TOKENIZE_HTTP_PATHS: tuple[str, ...] = ()
PREFILL_KEYS = (
    "prefill_s",
    "prefill_ms",
    "prefill_duration_s",
    "prefill_tokens_per_sec",
    "prefill_tok_s",
    "prefill_tokens_per_second",
)
_HEX_TO_HAN = {digit: HAN_HEX[i] for i, digit in enumerate("0123456789abcdef")}
_KEEPALIVE_RE = re.compile(r"keepalive\s+(\d+)\s*/\s*(\d+)", re.IGNORECASE)
_FREE_RE = re.compile(r"System-wide memory free percentage:\s*(\d+)%")
_PAGE_RE = re.compile(r"page size of (\d+) bytes", re.IGNORECASE)
_VM_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z \-]*):\s+(\d+)", re.MULTILINE)


def _kiln_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _protected_roots() -> list[Path]:
    roots = [
        Path("/Users/rainhuang/Desktop/models/kiln/benchmarks"),
        _kiln_root() / "benchmarks",
    ]
    out: list[Path] = []
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved not in out:
            out.append(resolved)
    return out


def _is_protected_output(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for root in _protected_roots():
        if resolved == root or root in resolved.parents:
            return True
    return False


def is_han(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
    )


def count_han(text: str) -> int:
    return sum(1 for ch in text if is_han(ch))


def han_encode(nonce: str, width: int) -> str:
    if width <= 0:
        return ""
    mapped = "".join(_HEX_TO_HAN[ch] for ch in nonce.lower() if ch in _HEX_TO_HAN)
    if not mapped:
        mapped = HAN_HEX[0]
    reps = (width + len(mapped) - 1) // len(mapped)
    return (mapped * reps)[:width]


def cjk_length_tag(n: int) -> str:
    width = min(8, n)
    digits = f"{n:0{width}d}" if width < 8 else f"{n:08d}"
    return han_encode(digits, width)


def cjk_block(n: int) -> str:
    if n < 1:
        raise ValueError("chars must be >= 1")
    if not CJK_UNIT or count_han(CJK_UNIT) != len(CJK_UNIT):
        raise ValueError("CJK_UNIT must be pure Han")
    tag = cjk_length_tag(n)
    rest = n - len(tag)
    if rest <= 0:
        return tag[:n]
    reps = (rest + len(CJK_UNIT) - 1) // len(CJK_UNIT)
    return tag + (CJK_UNIT * reps)[:rest]


def english_base(n: int) -> str:
    # Fixed width so bench-len-01000 is not a byte prefix of bench-len-10000.
    return f"bench-len-{n:05d}\n" + (ENGLISH_UNIT * n)


def cjk_text(n: int, mode: str, nonce: str | None) -> str:
    block = cjk_block(n)
    if mode == "identical":
        text = block
    else:
        if not nonce:
            raise ValueError("nonce required")
        slot = min(CJK_SLOT, n)
        coded = han_encode(nonce, slot)
        if mode == "partial":
            text = block[:-slot] + coded
        elif mode in {"fresh", "cold"}:
            text = coded + block[slot:]
        else:
            raise ValueError(mode)
    if len(text) != n or count_han(text) != n:
        raise ValueError("CJK length invariant failed")
    return text


def apply_nonce(base: str, mode: str, nonce: str | None) -> str:
    if mode == "identical":
        return base
    if mode not in {"partial", "fresh", "cold"}:
        raise ValueError(mode)
    if not nonce:
        raise ValueError("nonce required")
    if mode == "partial":
        return base + "\n" + nonce
    return nonce + "\n" + base


def shared_prefix_len(base: str, text: str) -> int:
    limit = min(len(base), len(text))
    index = 0
    while index < limit and base[index] == text[index]:
        index += 1
    return index


def build_prompt(
    *,
    mode: str,
    prompt_tokens: int | None,
    prompt_file: str | None,
    chars: int | None,
    nonce: str | None,
) -> dict:
    if chars is not None:
        base = cjk_block(chars)
        text = cjk_text(chars, mode, nonce)
        sizing = "cjk_chars"
        repeats = None
        requested_tokens = None
        requested_chars = chars
        file_path = None
        length_header = cjk_length_tag(chars)
    elif prompt_file:
        file_path = str(Path(prompt_file))
        base = Path(prompt_file).read_text(encoding="utf-8")
        if base == "":
            raise ValueError("prompt file is empty")
        text = apply_nonce(base, mode, nonce)
        sizing = "prompt_file"
        repeats = None
        requested_tokens = None
        requested_chars = None
        length_header = None
    elif prompt_tokens is not None:
        if prompt_tokens < 1:
            raise ValueError("prompt-tokens must be >= 1")
        base = english_base(prompt_tokens)
        text = apply_nonce(base, mode, nonce)
        sizing = "english_unit_repeats"
        repeats = prompt_tokens
        requested_tokens = prompt_tokens
        requested_chars = None
        file_path = None
        length_header = f"bench-len-{prompt_tokens:05d}"
    else:
        raise ValueError("need --prompt-tokens, --prompt-file, or --chars")
    return {
        "text": text,
        "sizing": sizing,
        "filler_repeats": repeats,
        "requested_prompt_tokens": requested_tokens,
        "requested_cjk_chars": requested_chars,
        "cjk_chars": count_han(text),
        "prompt_chars": len(text),
        "shared_prefix_chars": shared_prefix_len(base, text),
        "length_header": length_header,
        "nonce": nonce,
        "prompt_file": file_path,
        "prompt_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _pop_line(buf: str) -> tuple[str | None, str | None, str]:
    newline = buf.find("\n")
    carriage = buf.find("\r")
    if newline < 0 and carriage < 0:
        return None, None, buf
    if carriage >= 0 and (newline < 0 or carriage < newline):
        if carriage + 1 >= len(buf):
            return None, None, buf
        if buf[carriage + 1] == "\n":
            return buf[:carriage], "\r\n", buf[carriage + 2 :]
        return buf[:carriage], "\r", buf[carriage + 1 :]
    return buf[:newline], "\n", buf[newline + 1 :]


def _keepalive_nums(comment: str) -> tuple[int | None, int | None]:
    match = _KEEPALIVE_RE.search(comment)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


class SseAssembler:
    """Incremental SSE framing. One event is parsed alone; objects are not concatenated."""

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self._text = ""
        self._strip_bom = True
        self.utf8_errors = 0
        self._reset_event()

    def _reset_event(self) -> None:
        self._data_lines: list[str] = []
        self._comments: list[str] = []
        self._junk: list[str] = []
        self._event_name = "message"
        self._event_explicit = False

    def _decode(self, chunk: bytes, final: bool) -> str:
        try:
            return self._decoder.decode(chunk, final)
        except UnicodeDecodeError:
            self.utf8_errors += 1
            self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
            text = self._decoder.decode(chunk, final)
            if not final:
                self._decoder = codecs.getincrementaldecoder("utf-8")("strict")
            return text

    def feed(self, chunk: bytes, chunk_index: int, t_s: float) -> list[dict]:
        if not chunk:
            return []
        return self._push_text(self._decode(chunk, False), chunk_index, t_s)

    def finish(self, chunk_index: int, t_s: float) -> list[dict]:
        events = self._push_text(self._decode(b"", True), chunk_index, t_s)
        if self._text:
            self._accept_line(self._text, chunk_index, t_s)
            self._text = ""
        pending = self._dispatch(chunk_index, t_s, truncated=True)
        if pending:
            events.append(pending)
        return events

    def _push_text(self, text: str, chunk_index: int, t_s: float) -> list[dict]:
        if text:
            if self._strip_bom:
                text = text.lstrip("\ufeff")
                self._strip_bom = False
            self._text += text
        events: list[dict] = []
        while True:
            line, sep, rest = _pop_line(self._text)
            if sep is None:
                break
            self._text = rest
            event = self._accept_line(line, chunk_index, t_s)
            if event:
                events.append(event)
        return events

    def _accept_line(self, line: str, chunk_index: int, t_s: float) -> dict | None:
        if line == "":
            return self._dispatch(chunk_index, t_s, truncated=False)
        if line.startswith(":"):
            comment = line[1:]
            if comment.startswith(" "):
                comment = comment[1:]
            self._comments.append(comment)
            return None
        if ":" in line:
            name, value = line.split(":", 1)
            if value.startswith(" "):
                value = value[1:]
            field = name.lower()
            if field == "data":
                self._data_lines.append(value)
            elif field == "event":
                self._event_name = value
                self._event_explicit = True
            elif field in {"id", "retry"}:
                return None
            else:
                self._junk.append(line)
            return None
        self._junk.append(line)
        return None

    def _dispatch(self, chunk_index: int, t_s: float, truncated: bool) -> dict | None:
        if not (
            self._data_lines or self._comments or self._junk or self._event_explicit
        ):
            return None
        event_name = self._event_name
        payload = "\n".join(self._data_lines)
        comment = "\n".join(self._comments)
        junk = "\n".join(self._junk)
        has_data = bool(self._data_lines)
        self._reset_event()
        base = {
            "chunk_index": chunk_index,
            "t_s": t_s,
            "event_name": event_name,
            "truncated": truncated,
        }
        if junk and not has_data:
            base.update(kind="malformed", snippet=junk[:120])
            return base
        stripped = payload.strip()
        if has_data and stripped == "[DONE]":
            base.update(kind="done")
            return base
        if (not has_data) or stripped == "" or event_name.lower() in {"ping", "heartbeat"}:
            processed, total = _keepalive_nums(comment)
            base.update(
                kind="heartbeat",
                comment=comment[:200],
                processed=processed,
                total=total,
            )
            return base
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            base.update(kind="malformed", snippet=payload[:120])
            return base
        if not isinstance(obj, dict):
            base.update(kind="malformed", snippet=payload[:120])
            return base
        base.update(kind="json", payload=obj)
        return base


def _pieces(obj: dict) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    choices = obj.get("choices") or []
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            for key in ("delta", "message"):
                block = choice.get(key)
                if not isinstance(block, dict):
                    continue
                for field, kind in (
                    ("content", "content"),
                    ("reasoning", "reasoning"),
                    ("reasoning_content", "reasoning"),
                ):
                    value = block.get(field)
                    if isinstance(value, str) and value:
                        found.append((kind, value))
            text = choice.get("text")
            if isinstance(text, str) and text:
                found.append(("content", text))
    if "choices" not in obj:
        for field, kind in (
            ("content", "content"),
            ("reasoning", "reasoning"),
            ("reasoning_content", "reasoning"),
        ):
            value = obj.get(field)
            if isinstance(value, str) and value:
                found.append((kind, value))
    return found


def _finish_reason(obj: dict) -> str | None:
    choices = obj.get("choices") or []
    if isinstance(choices, list):
        for choice in choices:
            if isinstance(choice, dict) and choice.get("finish_reason"):
                return str(choice["finish_reason"])
    reason = obj.get("finish_reason")
    if isinstance(reason, str) and reason:
        return reason
    return None


def _extract_prefill(obj: dict) -> dict:
    containers: list[dict] = [obj]
    usage = obj.get("usage")
    if isinstance(usage, dict):
        containers.append(usage)
        details = usage.get("prompt_tokens_details")
        if isinstance(details, dict):
            containers.append(details)
    metrics = obj.get("metrics")
    if isinstance(metrics, dict):
        containers.append(metrics)
    found: dict = {}
    for container in containers:
        for key in PREFILL_KEYS:
            if container.get(key) is not None:
                found[key] = container[key]
    return found


def _prefill_seconds(fields: dict) -> float | None:
    try:
        if fields.get("prefill_s") is not None:
            return float(fields["prefill_s"])
        if fields.get("prefill_duration_s") is not None:
            return float(fields["prefill_duration_s"])
        if fields.get("prefill_ms") is not None:
            return float(fields["prefill_ms"]) / 1000.0
    except (TypeError, ValueError):
        return None
    return None


def prefill_report(fields: dict) -> dict:
    if not fields:
        return {
            "status": "client-unavailable",
            "reason": (
                "mlx-lm 0.31.3 usage has prompt_tokens, completion_tokens, total_tokens, "
                "and prompt_tokens_details.cached_tokens only. No prefill duration is reported. "
                ": keepalive N/M is uncached-tail progress, not prefill seconds."
            ),
        }
    return {
        "status": "reported",
        "fields": fields,
        "seconds": _prefill_seconds(fields),
    }


class StreamState:
    def __init__(self) -> None:
        self.ttft_s: float | None = None
        self.first_reasoning_s: float | None = None
        self.finish_reason: str | None = None
        self.saw_done = False
        self.usage: dict | None = None
        self.prefill_fields: dict = {}
        self.keepalive: list[dict] = []
        self.events: list[dict] = []
        self.chunk_times: list[dict] = []
        self.malformed_events = 0
        self.content_chars = 0
        self.reasoning_chars = 0
        self.content_events = 0
        self.reasoning_events = 0
        self.utf8_errors = 0
        self._event_index = 0

    def apply(self, event: dict) -> None:
        kind = event.get("kind")
        record = {
            "event_index": self._event_index,
            "chunk_index": event.get("chunk_index"),
            "t_s": event.get("t_s"),
            "kind": kind,
            "truncated": bool(event.get("truncated")),
        }
        self._event_index += 1
        if kind == "done":
            self.saw_done = True
            self.events.append(record)
            return
        if kind == "heartbeat":
            record["comment"] = event.get("comment") or ""
            processed = event.get("processed")
            total = event.get("total")
            record["processed"] = processed
            record["total"] = total
            if processed is not None and total is not None:
                self.keepalive.append(
                    {
                        "t_s": event.get("t_s"),
                        "chunk_index": event.get("chunk_index"),
                        "processed": processed,
                        "total": total,
                    }
                )
            self.events.append(record)
            return
        if kind == "malformed":
            self.malformed_events += 1
            record["snippet"] = event.get("snippet") or ""
            self.events.append(record)
            return
        if kind != "json":
            record["kind"] = "other"
            self.events.append(record)
            return
        payload = event["payload"]
        self.prefill_fields.update(_extract_prefill(payload))
        usage = payload.get("usage")
        if isinstance(usage, dict):
            self.usage = usage
        reason = _finish_reason(payload)
        if reason:
            self.finish_reason = reason
            record["finish_reason"] = reason
        pieces = _pieces(payload)
        content_chars = 0
        reasoning_chars = 0
        for piece_kind, text in pieces:
            if piece_kind == "content":
                self.content_events += 1
                self.content_chars += len(text)
                content_chars += len(text)
                if self.ttft_s is None:
                    self.ttft_s = event.get("t_s")
            else:
                self.reasoning_events += 1
                self.reasoning_chars += len(text)
                reasoning_chars += len(text)
                if self.first_reasoning_s is None:
                    self.first_reasoning_s = event.get("t_s")
        if content_chars:
            record["kind"] = "content"
            record["chars"] = content_chars
        elif reasoning_chars:
            record["kind"] = "reasoning"
            record["chars"] = reasoning_chars
        elif isinstance(usage, dict):
            record["kind"] = "usage"
        else:
            record["kind"] = "other"
        if reasoning_chars and content_chars:
            record["reasoning_chars"] = reasoning_chars
        self.events.append(record)


def completions_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/v1/chat/completions") or base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def _iso(unix: float) -> str:
    base = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(unix))
    millis = int((unix % 1) * 1000)
    return f"{base}.{millis:03d}Z"


def _cached_tokens(usage: dict | None) -> int | None:
    if not isinstance(usage, dict):
        return None
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict) and details.get("cached_tokens") is not None:
        return int(details["cached_tokens"])
    if usage.get("cached_tokens") is not None:
        return int(usage["cached_tokens"])
    return None


def _usage_int(usage: dict | None, key: str) -> int | None:
    if not isinstance(usage, dict) or usage.get(key) is None:
        return None
    return int(usage[key])


def build_note(mode: str, concurrency: int, sampled: bool) -> str:
    parts = [
        "prefill 仅在服务端 payload 带 prefill 耗时或 prefill tok/s 字段时记为 reported，否则为 client-unavailable。: keepalive N/M 是未缓存尾部进度，不是 prefill 秒数。",
        "requested_prompt_tokens 是英文单元重复次数，前面还有定宽 bench-len-##### 标头，不是 tokenizer 计数。禁止 len/4。权威计数是 usage.prompt_tokens（含聊天模板）。不同长度的标头故意错开，避免短 prompt 成为长 prompt 的字节前缀。",
        "TTFT 是首个非空 content delta。reasoning 不算 TTFT。decode_s = total_s - ttft_s，含结尾 usage 与 [DONE]。",
    ]
    if mode == "cold":
        parts.append("cold 只让 user 前缀唯一。脚本不重启服务，不能证明进程冷启动。")
    if mode == "identical":
        parts.append("identical 的汇总中位数混合了 run_index 0 与其后的命中。引用热缓存请用 by_run_index。")
    if concurrency > 1:
        parts.append("客户端并发不是服务端并行。现场 decode-concurrency 与 prompt-concurrency 都是 1，并发 2 测量排队。")
    if sampled:
        parts.append("memory_before 在本行。memory_after 在 stdout summary。采样不用 sudo。")
    else:
        parts.append("未采样内存。加 --sample-memory 才会读 memory_pressure 与 vm_stat。")
    return " ".join(parts)


def _empty_record(spec: dict, args: argparse.Namespace, url: str, note: str) -> dict:
    return {
        "schema": SCHEMA,
        "run_index": spec["run_index"],
        "prefix_mode": args.prefix_mode,
        "concurrency": args.concurrency,
        "base_url": args.base_url,
        "url": url,
        "model": args.model,
        "request_start_unix": None,
        "request_start_iso": None,
        "headers_s": None,
        "ttft_s": None,
        "first_reasoning_s": None,
        "decode_s": None,
        "total_s": None,
        "http_status": None,
        "finish_reason": None,
        "saw_done": False,
        "prompt_tokens": None,
        "prompt_tokens_source": None,
        "completion_tokens": None,
        "completion_tokens_source": None,
        "completion_tokens_approx": None,
        "cached_tokens": None,
        "decode_tok_s": None,
        "usage": None,
        "prefill": prefill_report({}),
        "keepalive": [],
        "chunk_times": [],
        "events": [],
        "requested_prompt_tokens": spec["requested_prompt_tokens"],
        "length_header": spec.get("length_header"),
        "filler_repeats": spec["filler_repeats"],
        "requested_cjk_chars": spec["requested_cjk_chars"],
        "cjk_chars": spec["cjk_chars"],
        "prompt_chars": spec["prompt_chars"],
        "shared_prefix_chars": spec["shared_prefix_chars"],
        "nonce": spec["nonce"],
        "prompt_sha256": spec["prompt_sha256"],
        "prompt_file": spec["prompt_file"],
        "sizing": spec["sizing"],
        "max_tokens": args.max_tokens,
        "read_size": READ_SIZE,
        "malformed_events": 0,
        "utf8_errors": 0,
        "content_chars": 0,
        "reasoning_chars": 0,
        "content_events": 0,
        "reasoning_events": 0,
        "error": None,
        "note": note,
        "memory_before": None,
    }


def _finalize_tokens(record: dict, state: StreamState) -> None:
    approx = state.content_events + state.reasoning_events
    record["completion_tokens_approx"] = approx
    usage = state.usage
    record["usage"] = usage
    prompt_tokens = _usage_int(usage, "prompt_tokens")
    completion = _usage_int(usage, "completion_tokens")
    if prompt_tokens is not None:
        record["prompt_tokens"] = prompt_tokens
        record["prompt_tokens_source"] = "usage"
    if completion is not None:
        record["completion_tokens"] = completion
        record["completion_tokens_source"] = "usage"
    elif state.events:
        record["completion_tokens"] = approx
        record["completion_tokens_source"] = "approx_delta_events"
    record["cached_tokens"] = _cached_tokens(usage)
    record["prefill"] = prefill_report(state.prefill_fields)
    decode_s = record.get("decode_s")
    if (
        record["completion_tokens_source"] == "usage"
        and isinstance(decode_s, (int, float))
        and decode_s > 0
        and completion
    ):
        record["decode_tok_s"] = completion / decode_s


def execute_chat(spec: dict, args: argparse.Namespace, url: str, note: str) -> dict:
    record = _empty_record(spec, args, url, note)
    body = {
        "model": args.model,
        "messages": [{"role": "user", "content": spec["text"]}],
        "max_tokens": args.max_tokens,
        **REQUEST_PIN,
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    state = StreamState()
    parser = SseAssembler()
    t0 = time.perf_counter()
    started = time.time()
    record["request_start_unix"] = started
    record["request_start_iso"] = _iso(started)
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            record["headers_s"] = time.perf_counter() - t0
            record["http_status"] = getattr(resp, "status", None)
            chunk_index = -1
            while True:
                chunk = resp.read(READ_SIZE)
                now = time.perf_counter() - t0
                if not chunk:
                    for event in parser.finish(chunk_index, now):
                        state.apply(event)
                    break
                chunk_index += 1
                state.chunk_times.append(
                    {"index": chunk_index, "t_s": now, "nbytes": len(chunk)}
                )
                for event in parser.feed(chunk, chunk_index, now):
                    state.apply(event)
                if state.saw_done:
                    break
    except urllib.error.HTTPError as exc:
        record["http_status"] = exc.code
        detail = exc.read(500).decode("utf-8", "replace")
        record["error"] = f"HTTP {exc.code}: {detail}"
    except Exception as exc:  # noqa: BLE001
        record["error"] = f"{type(exc).__name__}: {exc}"
    total_s = time.perf_counter() - t0
    record["total_s"] = total_s
    record["ttft_s"] = state.ttft_s
    record["first_reasoning_s"] = state.first_reasoning_s
    record["finish_reason"] = state.finish_reason
    record["saw_done"] = state.saw_done
    record["keepalive"] = state.keepalive
    record["chunk_times"] = state.chunk_times
    record["events"] = state.events
    record["malformed_events"] = state.malformed_events
    record["utf8_errors"] = parser.utf8_errors
    record["content_chars"] = state.content_chars
    record["reasoning_chars"] = state.reasoning_chars
    record["content_events"] = state.content_events
    record["reasoning_events"] = state.reasoning_events
    if state.ttft_s is not None:
        record["decode_s"] = max(0.0, total_s - state.ttft_s)
    _finalize_tokens(record, state)
    if record["error"] is None and not state.saw_done and record["http_status"] == 200:
        record["error"] = "stream ended without data: [DONE]"
    return record


def nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = math.ceil((percentile / 100.0) * len(ordered))
    index = min(len(ordered), max(1, rank)) - 1
    return ordered[index]


def _numeric(rows: list[dict], key: str) -> list[float]:
    found: list[float] = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            found.append(float(value))
    return found


def _stats(values: list[float]) -> dict:
    return {
        "n": len(values),
        "median": statistics.median(values) if values else None,
        "p95": nearest_rank(values, 95),
        "p95_method": "nearest_rank_ceil",
        "p95_stable": len(values) >= 20,
    }


def summarize(records: list[dict]) -> dict:
    rows = [row for row in records if isinstance(row, dict) and "run_index" in row]
    ttft = _numeric(rows, "ttft_s")
    ttft_stats = _stats(ttft)
    prefill_seconds: list[float] = []
    reported = 0
    for row in rows:
        prefill = row.get("prefill")
        if not isinstance(prefill, dict) or prefill.get("status") != "reported":
            continue
        reported += 1
        seconds = prefill.get("seconds")
        if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
            prefill_seconds.append(float(seconds))
    if reported == 0:
        prefill_summary: dict | str = "client-unavailable"
    else:
        prefill_summary = {
            "status": "reported",
            "n_runs": reported,
            **_stats(prefill_seconds),
        }
    by_index: dict[str, dict] = {}
    indexes: set[int] = set()
    for row in rows:
        index = int(row["run_index"])
        indexes.add(index)
        by_index.setdefault(str(index), []).append(row)  # type: ignore[arg-type]
    by_run_index = {
        key: _stats(_numeric(group, "ttft_s")) for key, group in sorted(by_index.items())
    }
    usage_decode_rows = [
        row
        for row in rows
        if row.get("completion_tokens_source") == "usage"
        and isinstance(row.get("decode_s"), (int, float))
    ]
    summary = {
        "schema": SCHEMA,
        "metric": "ttft_s",
        "n": ttft_stats["n"],
        "median": ttft_stats["median"],
        "p95": ttft_stats["p95"],
        "p95_method": ttft_stats["p95_method"],
        "p95_stable": ttft_stats["p95_stable"],
        "n_runs": len(rows),
        "n_errors": sum(1 for row in rows if row.get("error")),
        "ttft_s": ttft_stats,
        "prefill": prefill_summary,
        "by_run_index": by_run_index,
        "decode_s_usage_only": _stats(_numeric(usage_decode_rows, "decode_s")),
        "decode_tok_s_usage_only": _stats(_numeric(usage_decode_rows, "decode_tok_s")),
        "total_s": _stats(_numeric(rows, "total_s")),
        "cached_tokens": _stats(_numeric(rows, "cached_tokens")),
    }
    if 0 in indexes and any(index > 0 for index in indexes):
        summary["pool_warning"] = (
            "汇总中位数混合了 run_index 0 与其后的运行。identical 或 partial 要引用热前缀时，用 by_run_index，不要用 pooled median。"
        )
    return summary


def load_jsonl(path: str | Path) -> list[dict]:
    rows: list[dict] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def _run_command(argv: list[str]) -> dict:
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"argv": argv, "returncode": None, "error": f"{type(exc).__name__}: {exc}", "text": ""}
    text = (completed.stdout or "") + (completed.stderr or "")
    return {"argv": argv, "returncode": completed.returncode, "text": text}


def _vm_pages(text: str, label: str) -> int | None:
    for match in _VM_LINE_RE.finditer(text):
        if match.group(1).strip().lower() == label.lower():
            return int(match.group(2))
    return None


def compact_memory(sample: dict) -> dict:
    pressure = (sample.get("memory_pressure") or {}).get("text") or ""
    vm = (sample.get("vm_stat") or {}).get("text") or ""
    free = _FREE_RE.search(pressure)
    page = _PAGE_RE.search(vm) or _PAGE_RE.search(pressure)
    return {
        "free_pct": int(free.group(1)) if free else None,
        "page_size": int(page.group(1)) if page else None,
        "pages_free": _vm_pages(vm, "Pages free"),
        "pages_wired_down": _vm_pages(vm, "Pages wired down"),
        "pages_occupied_by_compressor": _vm_pages(vm, "Pages occupied by compressor"),
        "pages_stored_in_compressor": _vm_pages(vm, "Pages stored in compressor"),
        "swapins": _vm_pages(vm, "Swapins"),
        "swapouts": _vm_pages(vm, "Swapouts"),
    }


def sample_memory() -> dict:
    sample = {
        "memory_pressure": _run_command(["/usr/bin/memory_pressure"]),
        "vm_stat": _run_command(["/usr/bin/vm_stat"]),
    }
    sample["compact"] = compact_memory(sample)
    return sample


def _model_is_safe(model: str) -> str | None:
    if model == "default_model":
        return None
    path = Path(model)
    if path.is_dir():
        return None
    return (
        f"拒绝 --model {model!r}：mlx-lm 会把未知模型名交给 ModelProvider.load，"
        "可能触发下载或换掉已加载权重。只允许 default_model 或已经存在的本地目录。"
    )


def explain_tokenizer() -> int:
    message = """没有 HTTP tokenize 端点，本模式不会访问服务器，也不会下载 tokenizer。

已核对的路由（mlx-lm 0.31.3，venv 与 Homebrew 的 server.py 一致）：
  POST /v1/completions
  POST /v1/chat/completions
  POST /chat/completions
  GET  /v1/models
  GET  /health
内部 ResponseGenerator._tokenize 不是 HTTP 路由。
Kiln FastAPI 同样没有 /tokenize 或 /v1/tokenize；它的 POST /v1/chat/completions 是 BFF。

编排者在权重路径确定之后，用该目录里已有的 tokenizer.json 做本地计数。
不要 mlx_lm.load，不要从 Hub 下载。禁止 len(text)//4。
一次聊天的权威 prompt_tokens 是服务端 usage.prompt_tokens，其中包含聊天模板，
不等于 user 文本单独 tokenize 的长度。
"""
    print(message, end="", file=sys.stderr)
    print(
        json.dumps(
            {
                "schema": SCHEMA,
                "tokenize_http_paths": list(TOKENIZE_HTTP_PATHS),
                "action": "count_locally_after_weights_path_known",
                "download": False,
            },
            ensure_ascii=False,
        )
    )
    return 3


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="对已在运行的 mlx_lm.server 做聊天补全计时。不加载模型。",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8081")
    parser.add_argument("--model", default="default_model")
    parser.add_argument("--prompt-tokens", type=int, help="英文单元重复次数，不是已确认的 token 数")
    parser.add_argument("--prompt-file")
    parser.add_argument("--chars", type=int, help="纯汉字模式；矩阵使用 20000")
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument(
        "--prefix-mode",
        choices=("cold", "identical", "partial", "fresh"),
    )
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--out", help="JSONL 路径。每次运行覆盖。禁止写到 kiln/benchmarks")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--sample-memory", action="store_true")
    parser.add_argument(
        "--count-tokens",
        action="store_true",
        help="说明 tokenize 端点不存在，并要求本地计数。不访问网络。",
    )
    return parser.parse_args(argv)


def _validate(args: argparse.Namespace) -> str | None:
    if args.count_tokens:
        return None
    sources = [args.prompt_tokens is not None, bool(args.prompt_file), args.chars is not None]
    if sum(bool(item) for item in sources) != 1:
        return "需要且只能指定 --prompt-tokens、--prompt-file、--chars 之一。"
    if args.prefix_mode is None:
        return "需要 --prefix-mode {cold,identical,partial,fresh}。"
    if not args.out:
        return "需要 --out JSONL 路径。"
    if args.runs < 1 or args.concurrency < 1:
        return "--runs 与 --concurrency 都必须 >= 1。"
    if args.max_tokens < 1:
        return "--max-tokens 必须 >= 1。不要省略，否则服务端默认可能是 32768。"
    if args.timeout < 1:
        return "--timeout 必须 >= 1。"
    if args.prompt_tokens is not None and args.prompt_tokens < 1:
        return "--prompt-tokens 必须 >= 1。"
    if args.chars is not None and args.chars < 1:
        return "--chars 必须 >= 1。"
    if args.prefix_mode == "cold" and args.concurrency > 1:
        return "拒绝 cold 与 concurrency>1 同时使用。冷启动只允许并发 1。"
    if _is_protected_output(Path(args.out)):
        return "拒绝把 --out 写进 kiln/benchmarks。请写到 engineering/2026-09-24/raw/A4/。"
    model_error = _model_is_safe(args.model)
    if model_error:
        return model_error
    return None


def _build_jobs(args: argparse.Namespace) -> list[dict]:
    jobs: list[dict] = []
    for index in range(args.runs):
        nonce = None
        if args.prefix_mode != "identical":
            nonce = f"{index:04x}{uuid.uuid4().hex}"
        spec = build_prompt(
            mode=args.prefix_mode,
            prompt_tokens=args.prompt_tokens,
            prompt_file=args.prompt_file,
            chars=args.chars,
            nonce=nonce,
        )
        spec["run_index"] = index
        jobs.append(spec)
    return jobs


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if os.environ.get("KILN_ALLOW_BENCH") != "1":
        print(
            "拒绝运行：未设置 KILN_ALLOW_BENCH=1。本脚本不会自行设置该变量，也不会在未放行时访问推理端口。编排者确认 engineering/2026-09-24/ALLOW_BENCH 之后再导出该变量。",
            file=sys.stderr,
        )
        return 2
    if args.count_tokens:
        return explain_tokenizer()
    error = _validate(args)
    if error:
        print(error, file=sys.stderr)
        return 2
    if args.max_tokens > 512:
        print(
            "警告：max_tokens>512。主矩阵用 32，解码小格用 128。",
            file=sys.stderr,
        )
    try:
        jobs = _build_jobs(args)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"拒绝构造 prompt：{exc}", file=sys.stderr)
        return 2
    url = completions_url(args.base_url)
    note = build_note(args.prefix_mode, args.concurrency, args.sample_memory)
    memory_before = sample_memory() if args.sample_memory else None
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    records: list[dict] = []
    workers = min(args.concurrency, args.runs)

    def _one(spec: dict) -> None:
        try:
            record = execute_chat(spec, args, url, note)
        except Exception as exc:  # noqa: BLE001
            record = _empty_record(spec, args, url, note)
            record["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            spec["text"] = ""
        record.pop("text", None)
        record["memory_before"] = memory_before
        line = json.dumps(record, ensure_ascii=False)
        with lock:
            with out_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
            records.append(record)
        brief = {
            "run_index": record["run_index"],
            "http_status": record["http_status"],
            "ttft_s": record["ttft_s"],
            "prompt_tokens": record["prompt_tokens"],
            "cached_tokens": record["cached_tokens"],
            "error": record["error"],
        }
        print(json.dumps(brief, ensure_ascii=False), file=sys.stderr)

    out_path.write_text("", encoding="utf-8")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, spec) for spec in jobs]
        for future in futures:
            future.result()
    memory_after = sample_memory() if args.sample_memory else None
    records.sort(key=lambda row: row["run_index"])
    summary = summarize(records)
    summary["memory_before"] = memory_before
    summary["memory_after"] = memory_after
    summary["url"] = url
    summary["prefix_mode"] = args.prefix_mode
    summary["concurrency"] = args.concurrency
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if summary["n_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
