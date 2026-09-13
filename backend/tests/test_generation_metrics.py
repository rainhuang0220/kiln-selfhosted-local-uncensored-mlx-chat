from app.services.generation_metrics import compute_generation_metrics


def test_effective_rate_includes_ttft_decode_does_not():
    metrics = compute_generation_metrics(output_tokens=100, elapsed_s=10.0, ttft_s=8.0)
    assert metrics["ttft_ms"] == 8000
    assert metrics["total_latency_ms"] == 10000
    assert abs(metrics["effective_output_tokens_per_sec"] - 10.0) < 1e-6
    assert abs(metrics["decode_tokens_per_sec"] - 50.0) < 1e-6


def test_decode_window_starts_at_first_any_token():
    metrics = compute_generation_metrics(
        output_tokens=90,
        elapsed_s=10.0,
        ttft_s=8.0,
        first_any_s=1.0,
    )
    assert abs(metrics["decode_tokens_per_sec"] - 10.0) < 1e-6


def test_missing_ttft_does_not_invent_decode_rate():
    metrics = compute_generation_metrics(output_tokens=40, elapsed_s=4.0, ttft_s=None)
    assert metrics["effective_output_tokens_per_sec"] == 10.0
    assert metrics["decode_tokens_per_sec"] is None
