"""Check a model answer against evidence already in the source text.

Numbers and units come from the evidence. A mismatched model number is not kept.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_UNITS = (
    "摄氏度",
    "勒克斯",
    "毫米",
    "分钟",
    "小时",
    "公斤",
    "吨",
    "人",
    "张",
    "份",
    "箱",
    "米",
    "叶",
    "匹",
    "卷",
    "元",
)
_NUMBER = re.compile(r"(\d+(?:\.\d+)?)(" + "|".join(_UNITS) + r")?")


@dataclass(frozen=True)
class VerifiedAnswer:
    answer: str
    source: str
    model_number_ok: bool | None
    unit_restored: bool
    extra_context: bool


def minimal_evidence(text: str, quote: str) -> tuple[int, int, str]:
    start = text.find(quote)
    if start < 0:
        raise ValueError("quote is not in the source text")
    end = start + len(quote)
    return start, end, text[start:end]


def _unit_from_question(question: str) -> str:
    for unit in _UNITS:
        if unit in question:
            return unit
    return ""


def _numbers(text: str, unit: str) -> list[float]:
    found: list[float] = []
    for match in _NUMBER.finditer(text):
        value = float(match.group(1))
        got = match.group(2) or ""
        if unit and got and got != unit:
            continue
        if unit and not got:
            continue
        found.append(value)
    return found


def _labeled_number(text: str, label: str, unit: str) -> float | None:
    pattern = re.compile(
        re.escape(label) + r"[^。\n\d]{0,6}?(\d+(?:\.\d+)?)" + re.escape(unit)
    )
    match = pattern.search(text)
    if match is None:
        return None
    return float(match.group(1))


def _label_pair(question: str) -> tuple[str, str] | None:
    match = re.search(
        r"(.+?)比(.+?)(?:多多少|多几|高多少|低多少|少多少|增加|多|少)",
        question,
    )
    if match is None:
        return None
    left = match.group(1)
    left = re.sub(r"^.*中，", "", left)
    right = match.group(2)
    right = re.sub(r"(多印|多放水|多|少)$", "", right)
    return left.strip(), right.strip()


def _find_labeled(text: str, label: str, unit: str) -> float | None:
    for size in range(len(label), 3, -1):
        for start in range(0, len(label) - size + 1):
            found = _labeled_number(text, label[start : start + size], unit)
            if found is not None:
                return found
    return None


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _model_number(text: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", text or "")
    if match is None:
        return None
    return float(match.group(0))


def _same(left: float | None, right: float) -> bool:
    if left is None:
        return False
    return abs(left - right) < 1e-9


def _norm(text: str) -> str:
    return "".join((text or "").split())


def verify_answer(*, question: str, evidence: str, model_output: str) -> VerifiedAnswer:
    if "逐字" in question or "那一句" in question:
        return VerifiedAnswer(
            answer=evidence,
            source="evidence_quote",
            model_number_ok=True,
            unit_restored=False,
            extra_context=_norm(model_output) != _norm(evidence),
        )
    unit = _unit_from_question(question)
    flat = re.sub(r"\s+", "", evidence)
    pair = _label_pair(question)
    labeled: list[float] = []
    if pair is not None and unit:
        for label in pair:
            found = _find_labeled(flat, label, unit)
            if found is not None:
                labeled.append(found)
    if pair is not None and unit:
        if len(labeled) < 2:
            return VerifiedAnswer(
                answer="",
                source="insufficient_evidence",
                model_number_ok=None,
                unit_restored=False,
                extra_context=False,
            )
        value = abs(labeled[0] - labeled[1])
        source = "evidence_difference"
    elif any(mark in question for mark in ("还剩", "减去", "去掉", "实际用了", "超时")):
        return VerifiedAnswer(
            answer="",
            source="insufficient_evidence",
            model_number_ok=None,
            unit_restored=False,
            extra_context=False,
        )
    elif (values := _numbers(flat, unit)):
        value = values[-1]
        source = "evidence"
    else:
        return VerifiedAnswer(
            answer="",
            source="insufficient_evidence",
            model_number_ok=None,
            unit_restored=False,
            extra_context=False,
        )
    rendered = _format_number(value) + unit
    agreed = _same(_model_number(model_output), value)
    return VerifiedAnswer(
        answer=rendered,
        source=source,
        model_number_ok=agreed,
        unit_restored=unit != "" and unit not in (model_output or ""),
        extra_context=False,
    )
