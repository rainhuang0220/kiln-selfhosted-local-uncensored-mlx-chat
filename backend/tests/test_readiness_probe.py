import asyncio

from app.services.readiness_probe import run_readiness_probe


def test_health_does_not_generate_and_probe_marks_ready(client, chat_service, fake_provider):
    assert client.get("/health").json()["gateway"]["inference_capability"] == "UNVERIFIED"
    assert fake_provider.calls == []
    assert asyncio.run(run_readiness_probe(chat_service)) == "ready"
    body = client.get("/health").json()
    assert body["gateway"]["inference_capability"] == "READY"
    assert body["gateway"]["verification_method"] == "probe"
    assert body["inference"]["ready"] is True
    assert len(fake_provider.calls) == 1
    assert fake_provider.calls[0].max_tokens <= 16


def test_probe_does_not_treat_a_busy_queue_as_death(client, chat_service, fake_provider):
    chat_service._busy.add("conv")
    assert asyncio.run(run_readiness_probe(chat_service, busy=True)) == "skipped_busy"
    assert fake_provider.calls == []
    assert client.get("/health").json()["gateway"]["inference_capability"] == "BUSY"


def test_probe_failure_is_not_a_clean_ready(client, chat_service, fake_provider):
    async def dead(_request):
        raise RuntimeError("generation thread is not alive")

    fake_provider.complete = dead  # type: ignore[method-assign]
    assert asyncio.run(run_readiness_probe(chat_service)) == "failed"
    body = client.get("/health").json()
    assert body["provider"]["reachable"] is True
    assert body["gateway"]["inference_capability"] == "FAILED"
    assert body["inference"]["ready"] is False
