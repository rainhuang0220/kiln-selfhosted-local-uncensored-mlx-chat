from starlette.testclient import TestClient

from app.main import create_app
from app.services import accounts
from app.services.memory import MemoryService
from app.services.memory_provider import MemoryRecord


def test_memory_search_does_not_cross_accounts(tmp_settings, chat_service):
    mem: MemoryService = chat_service.memory
    mem.save(
        MemoryRecord(
            id="",
            memory_type="fact",
            key="alpha-slot",
            content="alpha-only memory",
            importance=0.9,
            user_id="user-a",
        )
    )
    mem.save(
        MemoryRecord(
            id="",
            memory_type="fact",
            key="beta-slot",
            content="beta-only memory",
            importance=0.9,
            user_id="user-b",
        )
    )
    hits_a = mem.search("memory", owner_id="user-a")
    hits_b = mem.search("memory", owner_id="user-b")
    assert [h.content for h in hits_a] == ["alpha-only memory"]
    assert [h.content for h in hits_b] == ["beta-only memory"]


def test_memory_http_is_owner_scoped(tmp_settings, chat_service):
    from app.services import accounts

    origin = "https://kiln.plainlist.space"
    tmp_settings.kiln_exposure = "private"
    tmp_settings.cookie_secure = True
    tmp_settings.kiln_public_origin = origin
    accounts.create_user("alpha", "correct-horse")
    accounts.create_user("beta", "correct-horse")
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(app, base_url=origin) as a, TestClient(app, base_url=origin) as b:
        assert a.post("/auth/login", json={"username": "alpha", "password": "correct-horse"}, headers={"Origin": origin}).status_code == 200
        assert b.post("/auth/login", json={"username": "beta", "password": "correct-horse"}, headers={"Origin": origin}).status_code == 200
        created = a.post("/memory", json={"content": "alpha private fact", "key": "city"}, headers={"Origin": origin})
        assert created.status_code == 200, created.text
        listed_b = b.get("/memory", params={"q": "private"})
        assert listed_b.status_code == 200
        assert listed_b.json()["data"] == []
        listed_a = a.get("/memory", params={"q": "private"})
        assert any("alpha private" in row["content"] for row in listed_a.json()["data"])


def test_retrieve_does_not_use_empty_conversation_as_query(chat_service):
    mem: MemoryService = chat_service.memory
    mem.save(
        MemoryRecord(
            id="",
            memory_type="fact",
            key="city",
            content="unrelated global leak",
            importance=0.9,
            user_id="other",
        )
    )
    hits = mem.retrieve("", "latest user text that is not in any memory", 256, owner_id="me")
    assert hits == []


def test_same_memory_key_is_allowed_for_different_owners(chat_service):
    mem: MemoryService = chat_service.memory
    mem.save(
        MemoryRecord(
            id="",
            memory_type="fact",
            key="city",
            content="alpha city",
            importance=0.5,
            user_id="user-a",
        )
    )
    mem.save(
        MemoryRecord(
            id="",
            memory_type="fact",
            key="city",
            content="beta city",
            importance=0.5,
            user_id="user-b",
        )
    )
    assert [h.content for h in mem.search("city", owner_id="user-a")] == ["alpha city"]
    assert [h.content for h in mem.search("city", owner_id="user-b")] == ["beta city"]
