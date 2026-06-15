from __future__ import annotations

import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


def test_rate_limited_key_is_skipped_until_cooldown_expires(monkeypatch):
    from core import api_key_manager
    from core.api_key_manager import APIKeyManager

    api_key_manager._GLOBAL_COOLDOWNS.clear()
    now = [100.0]
    monkeypatch.setattr(api_key_manager.time, "monotonic", lambda: now[0])
    monkeypatch.setenv("DUPLA_OPENAI_KEYS", "k1,k2,k3")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    manager = APIKeyManager()
    manager.mark_rate_limited("k1", 1.0)

    observed = [manager.next_key() for _ in range(3)]
    assert "k1" not in observed
    assert set(observed) <= {"k2", "k3"}

    now[0] += 1.1
    assert "k1" in [manager.next_key() for _ in range(4)]
