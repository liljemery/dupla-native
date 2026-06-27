"""Proyectos archivados + permisos de gerencia; revisión de gerencia en pipeline.

Revision ID: 047_project_archive_management_review
Revises: 046_remove_bootstrap_checklist
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.domain.permission_catalog import DEFAULT_ROLE_PERMISSIONS, PERMISSION_CATALOG

revision: str = "047_project_archive_management_review"
down_revision: Union[str, None] = "046_remove_bootstrap_checklist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_KEYS = (
    "lifecycle.management_review",
    "projects.archive",
    "projects.view_archived",
    "projects.delete",
)


def _ensure_permissions(conn) -> None:
    by_key = {p.key: p for p in PERMISSION_CATALOG}
    for key in _NEW_KEYS:
        perm = by_key[key]
        conn.execute(
            sa.text(
                "INSERT INTO permissions (key, label, category) VALUES (:key, :label, :category) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"key": perm.key, "label": perm.label, "category": perm.category},
        )
    gerencia_row = conn.execute(
        sa.text("SELECT id FROM roles WHERE slug = 'GERENCIA'"),
    ).fetchone()
    if gerencia_row is None:
        return
    role_id = str(gerencia_row[0])
    gerencia_keys = DEFAULT_ROLE_PERMISSIONS["GERENCIA"]
    for key in _NEW_KEYS:
        if key not in gerencia_keys:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_key, granted) "
                "VALUES (:role_id, :permission_key, true) ON CONFLICT DO NOTHING"
            ),
            {"role_id": role_id, "permission_key": key},
        )


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_projects_archived_at", "projects", ["archived_at"])
    conn = op.get_bind()
    _ensure_permissions(conn)


def downgrade() -> None:
    op.drop_index("ix_projects_archived_at", table_name="projects")
    op.drop_column("projects", "archived_at")
    conn = op.get_bind()
    for key in _NEW_KEYS:
        conn.execute(sa.text("DELETE FROM permissions WHERE key = :key"), {"key": key})
