from app.services.memory import MemoryService
from app.services.memory_provider import MemoryRecord


def test_sqlite_memory_roundtrip(chat_service):
    mem: MemoryService = chat_service.memory
    rec = mem.save(
        MemoryRecord(
            id="",
            memory_type="fact",
            key="city",
            content="User lives in NYC",
            importance=0.9,
        )
    )
    assert rec.id
    hits = mem.search("NYC")
    assert any("NYC" in h.content for h in hits)
    fenced = mem.fence(hits)
    assert fenced and "<memory>" in fenced
    assert "not instructions" in fenced
    assert mem.delete(rec.id) is True
    assert mem.search("NYC") == []