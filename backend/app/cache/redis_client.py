import json
from typing import Any, Optional, Union
from uuid import UUID

import redis.asyncio as redis

from app.config import get_settings


def scoped_redis_key(workspace_id: UUID, key: str) -> str:
    return f"{workspace_id}:{key}"


def ai_assistant_context_key(
    user_id: UUID,
    workspace_id: UUID,
    project_uuid: Optional[UUID] = None,
) -> str:
    base = f"ai:assistant:ctx:{user_id}"
    if project_uuid is None:
        return scoped_redis_key(workspace_id, base)
    return scoped_redis_key(workspace_id, f"{base}:p:{project_uuid}")


def chat_message_epoch_key(conversation_uuid: UUID, workspace_id: UUID) -> str:
    return scoped_redis_key(workspace_id, f"chat:msg_epoch:{conversation_uuid}")


async def cache_get_json(key: str) -> Optional[Union[dict[str, Any], list[Any]]]:
    settings = get_settings()
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        return None
    finally:
        await client.aclose()


async def cache_set_json(key: str, value: Union[dict[str, Any], list[Any]], ttl_seconds: int) -> None:
    settings = get_settings()
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.setex(key, ttl_seconds, json.dumps(value))
    except Exception:
        return
    finally:
        await client.aclose()


async def chat_message_epoch_get(conversation_uuid: UUID, workspace_id: UUID) -> int:
    settings = get_settings()
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw = await client.get(chat_message_epoch_key(conversation_uuid, workspace_id))
        if raw is None:
            return 0
        return int(raw)
    except Exception:
        return 0
    finally:
        await client.aclose()


async def chat_message_epoch_bump(conversation_uuid: UUID, workspace_id: UUID) -> int:
    settings = get_settings()
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        return int(await client.incr(chat_message_epoch_key(conversation_uuid, workspace_id)))
    except Exception:
        return 0
    finally:
        await client.aclose()


def _sanitize_ai_turns(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            out.append({"role": str(role), "content": content})
    return out


async def ai_assistant_context_load(
    user_id: UUID,
    workspace_id: UUID,
    project_uuid: Optional[UUID] = None,
) -> list[dict[str, str]]:
    key = ai_assistant_context_key(user_id, workspace_id, project_uuid)
    raw = await cache_get_json(key)
    return _sanitize_ai_turns(raw)


async def ai_assistant_context_save(
    user_id: UUID,
    workspace_id: UUID,
    turns: list[dict[str, str]],
    ttl_seconds: int,
    *,
    project_uuid: Optional[UUID] = None,
) -> None:
    key = ai_assistant_context_key(user_id, workspace_id, project_uuid)
    await cache_set_json(key, turns, ttl_seconds)
