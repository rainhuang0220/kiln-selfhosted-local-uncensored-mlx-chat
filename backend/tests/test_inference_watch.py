def test_health_names_degraded_inference_separately_from_http(client, chat_service):
    chat_service.note_inference_timeout("mlx timeout")
    chat_service.note_inference_timeout("mlx timeout")
    chat_service.note_inference_timeout("mlx timeout")
    body = client.get("/health").json()
    gateway = body["gateway"]
    assert gateway["state"] == "DEGRADED"
    assert gateway["transport_status"] == "ok"
    assert gateway["model_status"] == "http_ok"
    assert gateway["inference_status"] == "failed"
    assert gateway["inference_capability"] == "FAILED"
    assert gateway["suspension_reason"] is None
    assert body["provider"]["reachable"] is True


def test_health_names_video_park_even_if_port_is_up(client):
    client.app.state.media.lifecycle.state = "parked"
    client.app.state.media.lifecycle.reason = "video"
    body = client.get("/health").json()
    assert body["gateway"]["state"] == "VIDEO_SUSPENDED"
    assert body["gateway"]["suspension_reason"] == "video"


def test_video_park_wins_over_a_dead_port(client, fake_provider):
    async def down() -> bool:
        return False

    fake_provider.health = down  # type: ignore[method-assign]
    client.app.state.media.lifecycle.state = "parked"
    body = client.get("/health").json()
    assert body["provider"]["reachable"] is False
    assert body["gateway"]["state"] == "VIDEO_SUSPENDED"
    assert body["gateway"]["transport_status"] == "unreachable"
    assert body["gateway"]["suspension_reason"] == "video"


def test_health_names_busy_without_calling_the_model(client, chat_service, fake_provider):
    chat_service._busy.add("conv")
    body = client.get("/health").json()
    assert body["gateway"]["state"] == "BUSY"
    assert body["gateway"]["inference_status"] == "busy"
    assert fake_provider.calls == []


def test_three_timeouts_mark_inference_unhealthy(client, chat_service):
    fresh = client.get("/health").json()
    assert fresh["inference"]["ready"] is False
    assert fresh["gateway"]["inference_capability"] == "UNVERIFIED"
    assert fresh["status"] == "ok"
    chat_service.note_inference_timeout("mlx timeout")
    once = client.get("/health").json()
    assert once["inference"]["ready"] is False
    assert once["gateway"]["inference_capability"] == "DEGRADED"
    assert once["gateway"]["transport_status"] == "ok"
    assert once["status"] == "degraded"
    chat_service.note_inference_timeout("mlx timeout")
    chat_service.note_inference_timeout("mlx timeout")
    body = client.get("/health").json()
    assert body["inference"]["ready"] is False
    assert body["inference"]["consecutive_timeouts"] == 3
    assert body["gateway"]["inference_capability"] == "FAILED"
    assert body["status"] == "degraded"
    assert body["provider"]["reachable"] is True
    chat_service.note_inference_success()
    body = client.get("/health").json()
    assert body["inference"]["ready"] is True
    assert body["gateway"]["inference_capability"] == "READY"
    assert body["gateway"]["verification_method"] == "user_generation"
    assert body["gateway"]["evidence_expires_at"] > body["gateway"]["last_verified_at"]
    assert body["status"] == "ok"
