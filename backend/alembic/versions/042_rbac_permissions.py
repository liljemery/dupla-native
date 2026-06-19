"""Revision: RBAC permissions matrix

Revises: 041_clash_job_reanalysis
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

from app.domain.permission_catalog import (
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSION_CATALOG,
    SYSTEM_ROLE_LABELS,
)

revision = "042_rbac_permissions"
down_revision = "041_clash_job_reanalysis"
branch_labels = None
depends_on = None

SYSTEM_ROLE_UUIDS: dict[str, uuid.UUID] = {
    "GERENCIA": uuid.UUID("a0000001-0000-4000-8000-000000000001"),
    "CONTROL": uuid.UUID("a0000002-0000-4000-8000-000000000002"),
    "PRESUPUESTO": uuid.UUID("a0000003-0000-4000-8000-000000000003"),
    "ARQUITECTURA": uuid.UUID("a0000004-0000-4000-8000-000000000004"),
    "TEAM_LEADER": uuid.UUID("a0000005-0000-4000-8000-000000000005"),
}


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_deletable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_roles_slug", "roles", ["slug"], unique=True)
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("permission_key", sa.String(length=64), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["permission_key"], ["permissions.key"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_key"),
        sa.UniqueConstraint("role_id", "permission_key", name="uq_role_permission"),
    )
    op.create_table(
        "user_role_assignments",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role_assignment"),
    )
    op.create_table(
        "user_permission_overrides",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("permission_key", sa.String(length=64), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["permission_key"], ["permissions.key"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "permission_key"),
        sa.UniqueConstraint("user_id", "permission_key", name="uq_user_permission_override"),
    )

    conn = op.get_bind()
    for perm in PERMISSION_CATALOG:
        conn.execute(
            sa.text(
                "INSERT INTO permissions (key, label, category) VALUES (:key, :label, :category)"
            ),
            {"key": perm.key, "label": perm.label, "category": perm.category},
        )

    for slug, role_id in SYSTEM_ROLE_UUIDS.items():
        conn.execute(
            sa.text(
                "INSERT INTO roles (id, slug, name, is_system, is_deletable) "
                "VALUES (:id, :slug, :name, true, false)"
            ),
            {"id": str(role_id), "slug": slug, "name": SYSTEM_ROLE_LABELS[slug]},
        )

    for slug, granted_keys in DEFAULT_ROLE_PERMISSIONS.items():
        role_id = SYSTEM_ROLE_UUIDS[slug]
        for key in granted_keys:
            conn.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_key, granted) "
                    "VALUES (:role_id, :permission_key, true)"
                ),
                {"role_id": str(role_id), "permission_key": key},
            )

    users = conn.execute(sa.text("SELECT id, role::text, is_team_leader FROM users")).fetchall()
    role_slug_to_id = {slug: str(rid) for slug, rid in SYSTEM_ROLE_UUIDS.items()}
    for user_id, role_slug, is_team_leader in users:
        if role_slug in role_slug_to_id:
            conn.execute(
                sa.text(
                    "INSERT INTO user_role_assignments (user_id, role_id) "
                    "VALUES (:user_id, :role_id) ON CONFLICT DO NOTHING"
                ),
                {"user_id": str(user_id), "role_id": role_slug_to_id[role_slug]},
            )
        if is_team_leader:
            conn.execute(
                sa.text(
                    "INSERT INTO user_role_assignments (user_id, role_id) "
                    "VALUES (:user_id, :role_id) ON CONFLICT DO NOTHING"
                ),
                {"user_id": str(user_id), "role_id": role_slug_to_id["TEAM_LEADER"]},
            )

    op.drop_column("users", "is_team_leader")
    op.drop_column("users", "role")
    op.execute("DROP TYPE IF EXISTS user_role")


def downgrade() -> None:
    op.execute(
        "CREATE TYPE user_role AS ENUM ('GERENCIA', 'CONTROL', 'PRESUPUESTO', 'ARQUITECTURA')"
    )
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.Enum("GERENCIA", "CONTROL", "PRESUPUESTO", "ARQUITECTURA", name="user_role"),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column("is_team_leader", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    conn = op.get_bind()
    users = conn.execute(sa.text("SELECT id FROM users")).fetchall()
    for (user_id,) in users:
        assignments = conn.execute(
            sa.text(
                "SELECT r.slug FROM user_role_assignments ura "
                "JOIN roles r ON r.id = ura.role_id WHERE ura.user_id = :user_id"
            ),
            {"user_id": str(user_id)},
        ).fetchall()
        slugs = {row[0] for row in assignments}
        primary = next(
            (s for s in ("GERENCIA", "CONTROL", "PRESUPUESTO", "ARQUITECTURA") if s in slugs),
            "ARQUITECTURA",
        )
        conn.execute(
            sa.text("UPDATE users SET role = :role, is_team_leader = :tl WHERE id = :id"),
            {
                "role": primary,
                "tl": "TEAM_LEADER" in slugs,
                "id": str(user_id),
            },
        )

    op.alter_column("users", "role", nullable=False)
    op.drop_table("user_permission_overrides")
    op.drop_table("user_role_assignments")
    op.drop_table("role_permissions")
    op.drop_index("ix_roles_slug", table_name="roles")
    op.drop_table("roles")
    op.drop_table("permissions")
