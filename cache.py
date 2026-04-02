"""
Simple in-memory query cache with TTL.
"""

import time
import hashlib
import os
from typing import Any


class QueryCache:
    def __init__(self, ttl_seconds: int | None = None) -> None:
        self._ttl  = ttl_seconds or int(os.getenv("CACHE_TTL_SECONDS", 300))
        self._store: dict[str, tuple[float, Any]] = {}

    def _key(self, question: str) -> str:
        return hashlib.md5(question.strip().lower().encode()).hexdigest()

    def get(self, question: str) -> Any | None:
        key = self._key(question)
        if key in self._store:
            ts, value = self._store[key]
            if time.time() - ts < self._ttl:
                return value
            del self._store[key]
        return None

    def set(self, question: str, value: Any) -> None:
        self._store[self._key(question)] = (time.time(), value)

    def size(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()


# Singleton
query_cache = QueryCache()
