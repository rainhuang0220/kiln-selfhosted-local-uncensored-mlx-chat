import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.services.inference_watch import InferenceWatch, recovery_action


def test_fresh_watch_is_unverified():
    watch = InferenceWatch(now=lambda: 1_000)
    assert watch.capability(busy=False) == "UNVERIFIED"
    assert watch.snapshot()["ready"] is False
    assert watch.snapshot()["verification_method"] is None


def test_one_timeout_is_degraded_and_busy_is_not_death():
    watch = InferenceWatch(now=lambda: 1_000)
    watch.note_timeout("mlx timeout")
    assert watch.capability(busy=False) == "DEGRADED"
    assert watch.capability(busy=True) == "BUSY"
    assert watch.capability(busy=False) == "DEGRADED"


def test_third_timeout_is_failed_until_the_queue_is_idle():
    watch = InferenceWatch(now=lambda: 1_000)
    for _ in range(3):
        watch.note_timeout("mlx timeout")
    assert watch.capability(busy=True) == "BUSY"
    assert watch.capability(busy=False) == "FAILED"


def test_user_success_records_method_and_expiry():
    watch = InferenceWatch(ttl_ms=1_000, now=lambda: 5_000)
    watch.note_timeout("mlx timeout")
    watch.note_success(method="user_generation")
    snap = watch.snapshot()
    assert watch.capability(busy=False) == "READY"
    assert snap["verification_method"] == "user_generation"
    assert snap["last_verified_at"] == 5_000
    assert snap["evidence_expires_at"] == 6_000
    assert snap["ready"] is True


def test_expired_evidence_is_unverified_not_failed():
    now = {"t": 0}
    watch = InferenceWatch(ttl_ms=100, now=lambda: now["t"])
    watch.note_success(method="user_generation")
    now["t"] = 101
    assert watch.capability(busy=False) == "UNVERIFIED"
    assert watch.snapshot()["last_verified_at"] == 0


def test_unload_stays_failed_until_a_new_success():
    watch = InferenceWatch(now=lambda: 1)
    watch.note_success()
    watch.note_unloaded()
    assert watch.capability(busy=False) == "FAILED"
    watch.note_success(method="probe")
    assert watch.capability(busy=False) == "READY"
    assert watch.snapshot()["verification_method"] == "probe"


def test_http_200_with_dead_generate_fails_and_recovers_without_production_pid():
    state = {"dead": True}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def _json(self, code: int, payload: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            self._json(200, b'{"status":"ok"}')

        def do_POST(self):
            if state["dead"]:
                self._json(500, b'{"error":"generation thread is not alive"}')
                return
            self._json(200, b'{"choices":[{"finish_reason":"stop"}]}')

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    watch = InferenceWatch(now=lambda: 10_000)
    try:
        def probe() -> None:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as res:
                assert res.status == 200
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                data=b"{}",
                method="POST",
            )
            try:
                urllib.request.urlopen(req, timeout=2)
            except urllib.error.HTTPError as exc:
                assert exc.code == 500
                exc.close()
                watch.note_thread_dead("generation thread is not alive")
                return
            watch.note_success(method="probe")

        probe()
        assert watch.capability(busy=False) == "FAILED"
        assert recovery_action(capability="FAILED", busy=True) is None
        assert recovery_action(capability="FAILED", busy=False) == "restart_backend"
        state["dead"] = False
        probe()
        assert watch.capability(busy=False) == "READY"
        assert watch.snapshot()["verification_method"] == "probe"
    finally:
        httpd.shutdown()
        httpd.server_close()
