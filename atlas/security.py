import threading
import time
from collections import defaultdict, deque

from flask import jsonify, request


class InMemoryRateLimiter:
    """Limitador simples para a implantação local de processo único."""

    def __init__(self, requests_per_minute):
        self.limit = requests_per_minute
        self.events = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self):
        key = request.remote_addr or "local"
        now = time.monotonic()
        with self.lock:
            events = self.events[key]
            while events and events[0] <= now - 60:
                events.popleft()
            if len(events) >= self.limit:
                return jsonify({"erro": "Muitas requisições. Aguarde e tente novamente."}), 429
            events.append(now)
        return None


def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    )
    return response
