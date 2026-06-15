"""Round-robin API key selection for high-concurrency OpenAI stages."""

from __future__ import annotations

import os
import threading
import time

_GLOBAL_COOLDOWNS: dict[str, float] = {}
_GLOBAL_COOLDOWNS_LOCK = threading.Lock()


class APIKeyManager:
    """Cycle through configured API keys without logging or exposing them."""

    def __init__(
        self,
        *,
        env_var: str = "DUPLA_OPENAI_KEYS",
        fallback_env_var: str = "OPENAI_API_KEY",
    ) -> None:
        keys = [
            key.strip()
            for key in (os.getenv(env_var) or "").split(",")
            if key.strip()
        ]
        fallback = (os.getenv(fallback_env_var) or "").strip()
        if not keys and fallback:
            keys = [fallback]
        if not keys:
            raise ValueError(f"{env_var} or {fallback_env_var} must be set")

        self._keys = tuple(keys)
        self._index = 0
        self._lock = threading.Lock()

    @property
    def key_count(self) -> int:
        return len(self._keys)

    def mark_rate_limited(self, key: str, cooldown_seconds: float = 30.0) -> None:
        if not key:
            return
        with _GLOBAL_COOLDOWNS_LOCK:
            if key in self._keys:
                _GLOBAL_COOLDOWNS[key] = time.monotonic() + max(0.0, float(cooldown_seconds))

    def next_key(self) -> str:
        with self._lock:
            now = time.monotonic()
            key_count = len(self._keys)
            with _GLOBAL_COOLDOWNS_LOCK:
                cooldowns = dict(_GLOBAL_COOLDOWNS)
            best_cooled_key = self._keys[self._index]
            best_cooldown = cooldowns.get(best_cooled_key, 0.0)

            for offset in range(key_count):
                idx = (self._index + offset) % key_count
                candidate = self._keys[idx]
                cooldown_until = cooldowns.get(candidate, 0.0)
                if cooldown_until <= now:
                    self._index = (idx + 1) % key_count
                    return candidate
                if cooldown_until < best_cooldown:
                    best_cooldown = cooldown_until
                    best_cooled_key = candidate

            self._index = (self._keys.index(best_cooled_key) + 1) % key_count
            return best_cooled_key
