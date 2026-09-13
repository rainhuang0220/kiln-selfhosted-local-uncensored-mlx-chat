def test_three_timeouts_mark_inference_unhealthy(client, chat_service):
    assert client.get("/health").json()["inference"]["ready"] is True
    chat_service.note_inference_timeout("mlx timeout")
    chat_service.note_inference_timeout("mlx timeout")
    assert client.get("/health").json()["inference"]["ready"] is True
    chat_service.note_inference_timeout("mlx timeout")
    body = client.get("/health").json()
    assert body["inference"]["ready"] is False
    assert body["inference"]["consecutive_timeouts"] == 3
    assert body["status"] == "degraded"
    assert body["provider"]["reachable"] is True
    chat_service.note_inference_success()
    body = client.get("/health").json()
    assert body["inference"]["ready"] is True
    assert body["status"] == "ok"
