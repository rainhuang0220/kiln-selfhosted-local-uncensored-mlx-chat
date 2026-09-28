"""V21: related events under a character card need the full summary, up to 500 characters."""

from __future__ import annotations

LONG = ("陆遥把薄册子翻到右上角写着日期的那一页，请人自己看，再慢慢合上。" * 30)


def _draft(summary: str, event_id: str | None = "ev-1") -> dict:
    event = {"who": ["陆遥"], "summary": summary, "when": "那年"}
    if event_id:
        event["id"] = event_id
    return {
        "current_scene": "接待室",
        "me": {"identity": "顾客"},
        "characters": [{"name": "陆遥", "identity": "陆闻的姐姐"}],
        "timeline": [event],
    }


def test_s4_public_studio_payload_keeps_a_400_character_summary():
    from app.services.context_presets import public_studio_payload

    summary = LONG[:400]
    public = public_studio_payload(_draft(summary))
    assert public["timeline"][0]["summary"] == summary


def test_s4_summary_is_capped_at_500_even_without_an_event_id():
    from app.services.context_presets import public_studio_payload

    public = public_studio_payload(_draft(LONG, event_id=None))
    assert public["timeline"][0]["summary"] == LONG[:500]


def test_s4_storage_normalization_is_unchanged():
    from app.services.context_presets import normalize_payload

    assert len(normalize_payload(_draft(LONG[:400]))["timeline"][0]["summary"]) == 100
