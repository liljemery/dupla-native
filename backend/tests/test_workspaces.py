"""Workspace isolation and creation rules."""

import uuid

from app.cache.redis_client import ai_assistant_context_key, chat_message_epoch_key, scoped_redis_key
from app.domain.business_pliego import transition_blockers_for_business_pliego
from app.models.workspace import DEFAULT_WORKSPACE_UUID
from app.services.workspace_bootstrap_service import (
    general_conversation_uuid_for_workspace,
    task_list_uuid_for_workspace,
)


def test_general_conversation_uuid_per_workspace():
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    assert general_conversation_uuid_for_workspace(ws_a) != general_conversation_uuid_for_workspace(ws_b)


def test_task_lists_uuid_per_workspace():
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    assert task_list_uuid_for_workspace(ws_a, 0) != task_list_uuid_for_workspace(ws_b, 0)


def test_redis_keys_scoped_per_workspace():
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    user_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    assert scoped_redis_key(ws_a, "chat:messages") != scoped_redis_key(ws_b, "chat:messages")
    assert ai_assistant_context_key(user_id, ws_a) != ai_assistant_context_key(user_id, ws_b)
    assert chat_message_epoch_key(conv_id, ws_a) != chat_message_epoch_key(conv_id, ws_b)


def test_ga_fo_ok_with_stale_business_pliego_unapproved():
    from app.domain.ga_fo_01_arquitectura import expected_ga_fo_item_ids

    row = {"estado": "COMPLETO"}
    item_states = {k: dict(row) for k in expected_ga_fo_item_ids()}
    spec = {
        "ga_fo_01_arquitectura": {
            "schema_version": 1,
            "item_states": item_states,
            "approved": True,
        },
        "business_pliego": {
            "schema_version": 1,
            "sections": {},
            "approved": False,
        },
    }
    assert transition_blockers_for_business_pliego(spec) is None


def test_default_workspace_uuid_stable():
    assert DEFAULT_WORKSPACE_UUID == uuid.UUID("c0000001-0000-4000-8000-000000000001")
