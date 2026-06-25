"""Revision: canonical task board columns (3 per workspace)

Revises: 043_merge_alembic_heads
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

from app.domain.permission_catalog import DEFAULT_ROLE_PERMISSIONS, PERMISSION_CATALOG
from app.domain.task_board_constants import DEFAULT_TASK_LIST_TITLES, normalize_task_list_bucket, task_list_uuid_for_workspace

revision = "044_task_board_canonical_lists"
down_revision = "043_merge_alembic_heads"
branch_labels = None
depends_on = None


def _ensure_task_permission(conn) -> None:
    perm = next(p for p in PERMISSION_CATALOG if p.key == "tasks.board.edit")
    conn.execute(
        sa.text(
            "INSERT INTO permissions (key, label, category) VALUES (:key, :label, :category) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        {"key": perm.key, "label": perm.label, "category": perm.category},
    )
    for slug, granted_keys in DEFAULT_ROLE_PERMISSIONS.items():
        if perm.key not in granted_keys:
            continue
        role_row = conn.execute(
            sa.text("SELECT id FROM roles WHERE slug = :slug"),
            {"slug": slug},
        ).fetchone()
        if role_row is None:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_key, granted) "
                "VALUES (:role_id, :permission_key, true) ON CONFLICT DO NOTHING"
            ),
            {"role_id": str(role_row[0]), "permission_key": perm.key},
        )


def upgrade() -> None:
    conn = op.get_bind()

    ws_rows = conn.execute(sa.text("SELECT id FROM workspaces")).fetchall()
    workspace_ids = [uuid.UUID(str(row[0])) for row in ws_rows]
    orphan_rows = conn.execute(
        sa.text("SELECT DISTINCT workspace_id FROM task_lists WHERE workspace_id IS NOT NULL")
    ).fetchall()
    for row in orphan_rows:
        ws_id = uuid.UUID(str(row[0]))
        if ws_id not in workspace_ids:
            workspace_ids.append(ws_id)

    for ws_id in workspace_ids:
        canonical = [task_list_uuid_for_workspace(ws_id, i) for i in range(len(DEFAULT_TASK_LIST_TITLES))]
        for pos, (list_id, title) in enumerate(zip(canonical, DEFAULT_TASK_LIST_TITLES, strict=True)):
            existing = conn.execute(
                sa.text("SELECT id FROM task_lists WHERE id = :id"),
                {"id": str(list_id)},
            ).fetchone()
            if existing:
                conn.execute(
                    sa.text(
                        "UPDATE task_lists SET title = :title, position = :pos, workspace_id = :ws "
                        "WHERE id = :id"
                    ),
                    {"title": title, "pos": pos, "ws": str(ws_id), "id": str(list_id)},
                )
            else:
                conn.execute(
                    sa.text(
                        "INSERT INTO task_lists (id, workspace_id, title, position) "
                        "VALUES (:id, :ws, :title, :pos)"
                    ),
                    {"id": str(list_id), "ws": str(ws_id), "title": title, "pos": pos},
                )

        list_rows = conn.execute(
            sa.text("SELECT id, title FROM task_lists WHERE workspace_id = :ws"),
            {"ws": str(ws_id)},
        ).fetchall()
        canonical_set = {str(cid) for cid in canonical}
        for list_id, title in list_rows:
            if str(list_id) in canonical_set:
                continue
            bucket = normalize_task_list_bucket(str(title))
            target_id = canonical[bucket]
            conn.execute(
                sa.text("UPDATE task_cards SET list_id = :target WHERE list_id = :src"),
                {"target": str(target_id), "src": str(list_id)},
            )
            conn.execute(
                sa.text("DELETE FROM task_lists WHERE id = :id"),
                {"id": str(list_id)},
            )

    if conn.execute(sa.text("SELECT to_regclass('permissions')")).scalar() is not None:
        _ensure_task_permission(conn)


def downgrade() -> None:
    pass
