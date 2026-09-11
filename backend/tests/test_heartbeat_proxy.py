"""Idle-timeout proxy vs application heartbeats. No production proxy dependency."""

from __future__ import annotations

import json
import select
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import urllib.error
import urllib.request


class _IdleProxy:
    def __init__(self, target_port: int, idle_s: float):
        self.target_port = target_port
        self.idle_s = idle_s
        self.closed_idle = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass

    def _serve(self) -> None:
        while not self._stop.is_set():
            self.sock.settimeout(0.2)
            try:
                client, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._pipe, args=(client,), daemon=True).start()

    def _pipe(self, client: socket.socket) -> None:
        upstream = socket.create_connection(("127.0.0.1", self.target_port), timeout=2)
        try:
            sockets = [client, upstream]
            while True:
                readable, _, _ = select.select(sockets, [], [], self.idle_s)
                if not readable:
                    self.closed_idle = True
                    return
                for src in readable:
                    dst = upstream if src is client else client
                    data = src.recv(4096)
                    if not data:
                        return
                    dst.sendall(data)
        except (TimeoutError, socket.timeout, OSError):
            self.closed_idle = True
        finally:
            client.close()
            upstream.close()


def _serve(handler_cls) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _read(url: str, timeout: float) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def test_heartbeat_keeps_idle_proxy_open():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            deadline = time.time() + 0.7
            while time.time() < deadline:
                self.wfile.write(b"event: ping\ndata: {\"ok\":true}\n\n")
                self.wfile.flush()
                time.sleep(0.08)
            self.wfile.write(b"event: delta\ndata: {\"content\":\"hello\"}\n\n")
            self.wfile.flush()

        def log_message(self, fmt, *args):
            return

    server = _serve(Handler)
    proxy = _IdleProxy(server.server_address[1], idle_s=0.25)
    proxy.start()
    try:
        raw = _read(f"http://127.0.0.1:{proxy.port}/", timeout=2.0)
        assert "event: ping" in raw
        assert "hello" in raw
        assert raw.count("hello") == 1
        assert proxy.closed_idle is False
    finally:
        proxy.close()
        server.shutdown()


def test_missing_heartbeat_is_cut_by_idle_proxy():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"event: delta\ndata: {\"content\":\"hi\"}\n\n")
            self.wfile.flush()
            time.sleep(0.8)
            self.wfile.write(b"event: delta\ndata: {\"content\":\"late\"}\n\n")
            self.wfile.flush()

        def log_message(self, fmt, *args):
            return

    server = _serve(Handler)
    proxy = _IdleProxy(server.server_address[1], idle_s=0.2)
    proxy.start()
    try:
        try:
            raw = _read(f"http://127.0.0.1:{proxy.port}/", timeout=2.0)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            raw = ""
        assert "late" not in raw
        assert proxy.closed_idle is True
    finally:
        proxy.close()
        server.shutdown()


def test_ping_payload_is_not_assistant_text():
    ping = json.dumps({"ok": True})
    assert "雨" not in ping
    assert "content" not in json.loads(ping)
