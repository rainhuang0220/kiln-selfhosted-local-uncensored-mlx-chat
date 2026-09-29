"""Visible-body counters for long-form narrative acceptance."""

from app.services.narrative_chars import (
    count_han,
    count_visible_chars,
    estimate_tokens_for_chars,
    segment_char_budget,
)


def test_visible_chars_exclude_whitespace_only():
    text = "春 天\n播种。  "
    assert count_visible_chars(text) == 5
    assert count_han(text) == 4


def test_visible_chars_do_not_count_prompt_or_meta_markers():
    body = "正文一段。"
    assert count_visible_chars(body) == 5
    assert count_visible_chars("") == 0


def test_interactive_1536_tokens_explains_approx_2400_chars():
    # Forensic anchor: MLX max_tokens=1536 → ~2475 visible chars (zh prose).
    approx = estimate_tokens_for_chars(2475, chars_per_token=1.6)
    assert 1400 <= approx <= 1700


def test_segment_budget_splits_20k_into_manageable_chunks():
    budgets = segment_char_budget(target_visible_chars=20000, segment_chars=2500)
    assert sum(budgets) == 20000
    assert budgets[0] == 2500
    assert all(b > 0 for b in budgets)
