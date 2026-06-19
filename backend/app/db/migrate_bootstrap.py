"""Stamp Alembic when the DB schema exists but alembic_version is missing or empty."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from collections.abc import Callable

from sqlalchemy import inspect, text
from sqlalchemy.engine import Inspector
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

RevisionDetector = Callable[[Inspector], bool]

DEFAULT_WORKSPACE_ID = "c0000001-0000-4000-8000-000000000001"


def _table_names(inspector: Inspector) -> set[str]:
    return set(inspector.get_table_names())


def _column_names(inspector: Inspector, table: str) -> set[str]:
    if table not in _table_names(inspector):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _column_is_not_null(inspector: Inspector, table: str, column: str) -> bool:
    if table not in _table_names(inspector):
        return False
    for col in inspector.get_columns(table):
        if col["name"] == column:
            return not col.get("nullable", True)
    return False


# Newest first: first matching revision is stamped before `alembic upgrade head`.
_REVISION_DETECTORS: tuple[tuple[str, RevisionDetector], ...] = (
    (
        "042_rbac_permissions",
        lambda insp: "user_role_assignments" in _table_names(insp),
    ),
    (
        "038_workspace_backfill",
        lambda insp: _column_is_not_null(insp, "projects", "workspace_id"),
    ),
    (
        "037_workspace_fks",
        lambda insp: "workspace_id" in _column_names(insp, "projects"),
    ),
    (
        "036_workspaces",
        lambda insp: "workspaces" in _table_names(insp),
    ),
    (
        "035_user_is_team_leader",
        lambda insp: "is_team_leader" in _column_names(insp, "users"),
    ),
    (
        "034_user_must_change_password",
        lambda insp: "must_change_password" in _column_names(insp, "users"),
    ),
    (
        "033_password_reset_tokens",
        lambda insp: "password_reset_tokens" in _table_names(insp),
    ),
    (
        "032_clash_job_export_metadata",
        lambda insp: "folder_id" in _column_names(insp, "project_clash_jobs"),
    ),
    (
        "031_project_clash_jobs",
        lambda insp: "project_clash_jobs" in _table_names(insp),
    ),
    (
        "030_project_budget_jobs",
        lambda insp: "project_budget_jobs" in _table_names(insp),
    ),
    (
        "029_project_price_database_files",
        lambda insp: "project_price_database_files" in _table_names(insp),
    ),
    (
        "019_workflow_templates",
        lambda insp: "workflow_templates" in _table_names(insp),
    ),
    (
        "018_project_doc_alignment",
        lambda insp: "project_technical_findings" in _table_names(insp),
    ),
    (
        "017_user_names",
        lambda insp: "first_name" in _column_names(insp, "users"),
    ),
    (
        "015_project_file_folders",
        lambda insp: "project_file_folders" in _table_names(insp),
    ),
    (
        "007_plan_delivery_requests",
        lambda insp: "plan_delivery_requests" in _table_names(insp),
    ),
    (
        "006_project_members",
        lambda insp: "project_members" in _table_names(insp),
    ),
    (
        "005_project_workflow",
        lambda insp: "project_events" in _table_names(insp),
    ),
    (
        "004_chat_conversations",
        lambda insp: "chat_conversations" in _table_names(insp),
    ),
    (
        "002_chat_task_board",
        lambda insp: "task_cards" in _table_names(insp),
    ),
    (
        "001_initial",
        lambda insp: "modules" in _table_names(insp),
    ),
)


def _alembic_version_row(inspector: Inspector, connection) -> str | None:
    if "alembic_version" not in inspector.get_table_names():
        return None
    row = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
    if row is None:
        return ""
    return str(row[0])


def detect_legacy_revision(inspector: Inspector) -> str | None:
    if "modules" not in _table_names(inspector):
        return None
    for revision, matches in _REVISION_DETECTORS:
        if matches(inspector):
            return revision
    return None


def _ensure_default_workspace(connection) -> None:
    inspector = inspect(connection)
    if "workspaces" not in _table_names(inspector):
        return
    count = connection.execute(text("SELECT COUNT(*) FROM workspaces")).scalar_one()
    if count:
        return
    connection.execute(
        text(
            "INSERT INTO workspaces (id, name, created_at, updated_at) "
            "VALUES (:id, NULL, NOW(), NOW())"
        ),
        {"id": DEFAULT_WORKSPACE_ID},
    )
    connection.commit()
    print(
        "[migrate_bootstrap] Inserted default workspace row missing from legacy schema",
        file=sys.stderr,
    )


def _bootstrap_on_connection(connection) -> None:
    inspector = inspect(connection)
    current = _alembic_version_row(inspector, connection)
    if current:
        _ensure_default_workspace(connection)
        return

    revision = detect_legacy_revision(inspector)
    if revision is None:
        return

    print(
        f"[migrate_bootstrap] Schema exists without Alembic revision; stamping {revision}",
        file=sys.stderr,
    )
    subprocess.run(["alembic", "stamp", revision], check=True)
    _ensure_default_workspace(connection)


async def bootstrap_alembic_if_needed() -> None:
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_bootstrap_on_connection)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(bootstrap_alembic_if_needed())


if __name__ == "__main__":
    main()
