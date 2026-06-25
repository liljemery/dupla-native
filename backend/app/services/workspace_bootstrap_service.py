from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_conversation import ChatConversation, ChatConversationKind
from app.domain.task_board_constants import DEFAULT_TASK_LIST_TITLES, task_list_uuid_for_workspace
from app.models.task_board import TaskList
from app.models.workflow_template import WorkflowTemplate, WorkflowTemplateStep
from app.seed_default_workflow_template import _LEGACY_PHASE_TITLE, _legacy_step_id, _legacy_template_id, _title_to_stable_key


def general_conversation_uuid_for_workspace(workspace_id: UUID) -> UUID:
    return uuid.uuid5(workspace_id, "dupla:general_conversation")


def workflow_template_uuid_for_workspace(workspace_id: UUID) -> UUID:
    return uuid.uuid5(workspace_id, "dupla:workflow_template:legacy")


async def bootstrap_workspace_resources(session: AsyncSession, workspace_id: UUID) -> None:
    """Create per-workspace GENERAL chat, task lists, and default workflow template."""
    now = datetime.now(timezone.utc)

    general_id = general_conversation_uuid_for_workspace(workspace_id)
    existing_general = await session.get(ChatConversation, general_id)
    if existing_general is None:
        session.add(
            ChatConversation(
                id=general_id,
                kind=ChatConversationKind.GENERAL,
                title=None,
                created_at=now,
                last_message_at=None,
                project_id=None,
                workspace_id=workspace_id,
            )
        )

    for position, title in enumerate(DEFAULT_TASK_LIST_TITLES):
        list_id = task_list_uuid_for_workspace(workspace_id, position)
        existing_list = await session.get(TaskList, list_id)
        if existing_list is None:
            session.add(
                TaskList(
                    id=list_id,
                    workspace_id=workspace_id,
                    title=title,
                    position=position,
                )
            )

    template_id = workflow_template_uuid_for_workspace(workspace_id)
    existing_template = await session.get(WorkflowTemplate, template_id)
    if existing_template is None:
        session.add(
            WorkflowTemplate(
                id=template_id,
                workspace_id=workspace_id,
                name="Flujo estándar Dupla",
                description="Plantilla por defecto con los pasos del proceso operativo.",
                icon_key="GitBranch",
                created_by_user_id=None,
                archived_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
        used: set[str] = set()
        for idx, (old_sk, step_title) in enumerate(_LEGACY_PHASE_TITLE):
            base = _title_to_stable_key(step_title, idx)
            candidate = base
            n_dup = 2
            while candidate in used:
                candidate = f"{base}_{n_dup}"
                n_dup += 1
            used.add(candidate)
            sid = uuid.uuid5(template_id, f"step:{old_sk}")
            session.add(
                WorkflowTemplateStep(
                    id=sid,
                    workflow_template_id=template_id,
                    sort_index=idx,
                    stable_key=candidate,
                    title=step_title,
                    icon_key="GitBranch",
                    behavior_kind=old_sk,
                    blocked_by_step_id=None,
                    requires_approval_role=None,
                    on_enter_actions=[],
                    created_at=now,
                    updated_at=now,
                )
            )

    await session.flush()
