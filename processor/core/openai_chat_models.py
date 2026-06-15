"""
Shared OpenAI Chat Completions model selection for Dupla.

Defaults to GPT-5.4. GPT-5.x uses max_completion_tokens + reasoning_effort;
older chat models use max_tokens + temperature.

Environment (optional, see .env):
  OPENAI_CHAT_MODEL — classifier + CAD layer GPT (default: gpt-5.4)
  OPENAI_VISION_MODEL — plan image vision; if unset, same as OPENAI_CHAT_MODEL
  OPENAI_CHAT_MAX_OUTPUT — default max completion tokens for chat helpers (4096)
  OPENAI_VISION_MAX_OUTPUT — vision pages (default 4096)
  OPENAI_CHAT_REASONING_EFFORT — gpt-5.x: none | low | medium | high (default none)
  OPENAI_VISION_REASONING_EFFORT — overrides chat reasoning for vision only if set
  OPENAI_CHAT_TEMPERATURE — gpt-4 family only (default 0.1)
  OPENAI_VISION_TEMPERATURE — gpt-4 vision only; falls back to OPENAI_CHAT_TEMPERATURE
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_CHAT_MODEL = "gpt-5.4"


def chat_model_id(explicit: str | None = None) -> str:
    """Model for BC3 classifier and CAD layer classification."""
    if explicit is not None:
        s = explicit.strip()
        return s or DEFAULT_CHAT_MODEL
    raw = (os.getenv("OPENAI_CHAT_MODEL") or "").strip()
    return raw or DEFAULT_CHAT_MODEL


def vision_model_id(explicit: str | None = None) -> str:
    """Model for plan vision; OPENAI_VISION_MODEL or OPENAI_CHAT_MODEL or default."""
    if explicit is not None:
        s = explicit.strip()
        return s or chat_model_id()
    raw = (os.getenv("OPENAI_VISION_MODEL") or "").strip()
    if raw:
        return raw
    return chat_model_id()


def _clamp_int(value: str | None, default: int, lo: int, hi: int) -> int:
    if not (value or "").strip():
        return default
    try:
        n = int(str(value).strip())
    except ValueError:
        return default
    return max(lo, min(n, hi))


def chat_max_output_tokens() -> int:
    return _clamp_int(os.getenv("OPENAI_CHAT_MAX_OUTPUT"), 4096, 256, 128_000)


def vision_max_output_tokens() -> int:
    return _clamp_int(os.getenv("OPENAI_VISION_MAX_OUTPUT"), 4096, 256, 128_000)


def reasoning_effort_for_chat() -> str:
    return (os.getenv("OPENAI_CHAT_REASONING_EFFORT") or "none").strip() or "none"


def reasoning_effort_for_vision() -> str:
    v = (os.getenv("OPENAI_VISION_REASONING_EFFORT") or "").strip()
    if v:
        return v
    return reasoning_effort_for_chat()


def uses_gpt5_completion_style(model: str) -> bool:
    return model.lower().startswith("gpt-5")


def chat_temperature() -> float:
    try:
        return float((os.getenv("OPENAI_CHAT_TEMPERATURE") or "0.1").strip() or "0.1")
    except ValueError:
        return 0.1


def vision_temperature() -> float:
    raw = (os.getenv("OPENAI_VISION_TEMPERATURE") or os.getenv("OPENAI_CHAT_TEMPERATURE") or "0.1").strip() or "0.1"
    try:
        return float(raw)
    except ValueError:
        return 0.1


def create_chat_completion(
    client: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_output_tokens: int,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
) -> Any:
    """
    Chat Completions with parameters compatible with GPT-5.x vs GPT-4 family.
    If reasoning_effort is None, uses chat reasoning defaults (callers should pass
    reasoning_effort_for_vision() for vision).
    """
    kwargs: dict[str, Any] = {"model": model, "messages": messages}
    if uses_gpt5_completion_style(model):
        kwargs["max_completion_tokens"] = max_output_tokens
        eff = (reasoning_effort if reasoning_effort is not None else reasoning_effort_for_chat()).strip() or "none"
        kwargs["reasoning_effort"] = eff
    else:
        kwargs["max_tokens"] = max_output_tokens
        kwargs["temperature"] = chat_temperature() if temperature is None else float(temperature)
    return client.chat.completions.create(**kwargs)
