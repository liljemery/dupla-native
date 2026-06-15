from __future__ import annotations

import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


class _TransientOpenAIError(Exception):
    status_code = 429


class _Message:
    content = '{"walls":[],"doors":[],"windows":[],"fixtures":[],"structural_elements":[]}'


class _Choice:
    message = _Message()


class _Response:
    choices = [_Choice()]


def test_vision_retry_rotates_key_after_429(tmp_path, monkeypatch):
    from agents import vision_agent
    from core import api_key_manager

    api_key_manager._GLOBAL_COOLDOWNS.clear()
    monkeypatch.setenv("DUPLA_OPENAI_KEYS", "k1,k2")
    monkeypatch.setenv("OPENAI_VISION_MAX_RETRIES", "2")
    monkeypatch.setenv("OPENAI_VISION_RETRY_BASE_SECONDS", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    vision_agent._KEY_MANAGER = None
    monkeypatch.setattr(vision_agent, "HAS_OPENAI", True)

    image_path = tmp_path / "page_0001.png"
    image_path.write_bytes(b"fake")

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

    attempts: list[str] = []

    def fake_vision_chat_completion(client, *, model, messages):
        attempts.append(client.api_key)
        if len(attempts) == 1:
            raise _TransientOpenAIError("rate limited")
        return _Response()

    monkeypatch.setattr(vision_agent, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(vision_agent, "_vision_chat_completion", fake_vision_chat_completion)
    monkeypatch.setattr(vision_agent.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(vision_agent.random, "random", lambda: 0.0)

    result = vision_agent._analyze_plan_uncached(image_path, {}, "level_01")

    assert result["level_id"] == "level_01"
    assert attempts == ["k1", "k2"]
