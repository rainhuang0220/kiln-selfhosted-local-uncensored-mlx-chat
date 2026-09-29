import pytest

from app.services.providers.dzmm import DzmmQuotaError, card_from_context, model_catalog, preferred_model
from app.services.providers.dzmm import read_token, write_token
from app.services.providers.dzmm import parse_character_card
from app.services.providers.dzmm import DzmmProvider
from app.providers.base import ChatRequest
import httpx


def test_free_tier_is_default_only_with_token():
    assert preferred_model(False) == "local:9b"
    assert preferred_model(True) == "nalang-turbo-0826"
    rows = model_catalog()
    assert {"nalang-turbo-0826", "nalang-xl-0826", "nalang-max-0826", "local:9b"} <= {r["id"] for r in rows}
    assert next(r for r in rows if r["id"] == "nalang-xl-0826")["label"] == "推荐付费 / 文爱更好"


def test_card_clips_source_and_keeps_scene():
    frame = {"active_character": {"name": "阿青", "description": "技师"}, "active_scene": "接待室"}
    card = card_from_context(frame, "角色说明。" + "甲" * 3000 + "EVENT_LEDGER" + "小学日记" * 100)
    assert card["name"] == "阿青"
    assert "接待室" in card["scenario"]
    assert len(card["description"]) <= 2400
    assert "EVENT_LEDGER" not in card["description"]
    assert "小学日记" not in card["description"]


def test_cloud_body_sends_card_and_last_user_without_local_ledger():
    frame = {"active_character": {"name": "阿青"}, "active_scene": "接待室"}
    card = card_from_context(frame, "角色设定。" + "EVENT_LEDGER 旧事")
    request = ChatRequest(messages=[
        {"role": "system", "content": "EVENT_LEDGER" * 500},
        {"role": "user", "content": "你靠近一点"},
    ], extra={"dzmm_card": card})
    body = DzmmProvider("test-token")._payload(request, True)
    assert body["model"] == "nalang-turbo-0826"
    assert body["messages"] == [{"role": "user", "content": "你靠近一点"}]
    assert body["card"]["scenario"] == "接待室"
    assert "EVENT_LEDGER" not in str(body)
    assert body["enable_thinking"] is False


def test_named_recall_only_adds_matching_person():
    frame = {
        "active_character": {"name": "阿青"}, "active_scene": "接待室",
        "references": {"people": [{"name": "陆遥"}, {"name": "沈乔"}],
                       "events": [{"who": ["陆遥"], "gist": "陆遥的旧事"},
                                  {"who": ["沈乔"], "gist": "沈乔的旧事"}]},
    }
    assert "旧事" not in card_from_context(frame, recall_query="你好")["description"]
    named = card_from_context(frame, recall_query="陆遥是谁")["description"]
    assert "陆遥的旧事" in named
    assert "沈乔的旧事" not in named


@pytest.mark.asyncio
async def test_http_400_quota_message_requests_local_fallback():
    def respond(request):
        return httpx.Response(400, json={"error": {"code": "insufficient_quota", "message": "额度用尽"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = DzmmProvider("test-token", client=client)
        with pytest.raises(DzmmQuotaError):
            await provider.complete(ChatRequest(messages=[{"role": "user", "content": "好"}]))


def test_quota_error_identifies_both_statuses():
    assert DzmmQuotaError(402).status == 402
    assert DzmmQuotaError(429).status == 429


def test_token_is_stored_with_private_permissions(tmp_settings):
    import stat
    from app.services.providers.dzmm import token_path

    write_token(tmp_settings.sqlite_path, "secret-value")
    assert read_token(tmp_settings.sqlite_path) == "secret-value"
    assert stat.S_IMODE(token_path(tmp_settings.sqlite_path).stat().st_mode) == 0o600


@pytest.mark.parametrize("status", [402, 429])
@pytest.mark.asyncio
async def test_quota_falls_back_to_local_in_same_stream(chat_service, fake_provider, status):
    class QuotaCloud:
        async def stream(self, request):
            raise DzmmQuotaError(status)
            yield  # Keep this an async generator.

    events = [event async for event in chat_service.chat(
        message="好", conversation_id=None, stream=True, profile="interactive_dialogue",
        enable_thinking=False, auto_continue=False,
        selected_model="nalang-turbo-0826", provider_override=QuotaCloud(),
    )]
    assert any(e["event"] == "status" and "已改用本机" in e["data"]["stage"] for e in events)
    assert any(e["event"] == "delta" and "echo:" in e["data"].get("content", "") for e in events)
    assert fake_provider.calls


def test_import_tavern_v2_json_and_png():
    import base64
    import json
    import struct
    import zlib

    payload = {"spec": "chara_card_v2", "data": {"name": "阿青", "description": "成年技师", "scenario": "接待室"}}
    raw = json.dumps(payload, ensure_ascii=False).encode()
    assert parse_character_card(raw, "a.json")["name"] == "阿青"
    chunk = b"chara\0" + base64.b64encode(raw)
    png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", len(chunk)) + b"tEXt" + chunk
    png += struct.pack(">I", zlib.crc32(b"tEXt" + chunk))
    assert parse_character_card(png, "a.png")["description"] == "成年技师"


def test_settings_and_card_import_routes_keep_token_private(client, tmp_settings):
    import json

    saved = client.put("/models/dzmm/settings", json={"api_token": "secret-value"})
    assert saved.status_code == 200
    assert "secret-value" not in saved.text
    settings = client.get("/models/dzmm/settings")
    assert settings.json()["default_model"] == "nalang-turbo-0826"
    assert "secret-value" not in settings.text
    card = client.post("/context/cards/import?filename=test.json", content=json.dumps({
        "spec": "chara_card_v2", "data": {"name": "阿青", "description": "技师", "tags": ["接待室"]},
    }).encode())
    assert card.status_code == 200
    library = client.get("/context/cards/library").json()["data"]
    assert next(row for row in library if row["name"] == "阿青")["tags"] == ["接待室"]
