"""
Simple sliding-window rate limiter keyed by client IP.
"""

import time
import os
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_per_minute: int | None = None) -> None:
        self._max = max_per_minute or int(os.getenv("RATE_LIMIT_PER_MINUTE", 30))
        self._window = 60  # seconds
        self._calls: dict[str, deque] = defaultdict(deque)

    def is_allowed(self, client_id: str) -> bool:
        now   = time.time()
        calls = self._calls[client_id]

        # Drop old entries outside the window
        while calls and now - calls[0] > self._window:
            calls.popleft()

        if len(calls) >= self._max:
            return False

        calls.append(now)
        return True

    def remaining(self, client_id: str) -> int:
        now   = time.time()
        calls = self._calls[client_id]
        while calls and now - calls[0] > self._window:
            calls.popleft()
        return max(0, self._max - len(calls))


rate_limiter = RateLimiter()
