"""architecture_revisions.revision_role for display by discipline.

Revision ID: 025_architecture_revision_role
Revises: 024_project_responsible_external
Create Date: 2026-05-01

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "025_architecture_revision_role"
down_revision: Union[str, None] = "024_project_responsible_external"


def upgrade() -> None:
    op.add_column(
        "architecture_revisions",
        sa.Column(
            "revision_role",
            sa.String(length=32),
            nullable=False,
            server_default="ARQUITECTURA",
        ),
    )
    op.execute("ALTER TABLE architecture_revisions ALTER COLUMN revision_role DROP DEFAULT")


def downgrade() -> None:
    op.drop_column("architecture_revisions", "revision_role")
