"""Icon per workflow_template_step (Lucide key); backfill from template.

Revision ID: 023_step_icon_key
Revises: 022_project_kind_v2
Create Date: 2026-05-01

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "023_step_icon_key"
down_revision: Union[str, None] = "022_project_kind_v2"


def upgrade() -> None:
    op.add_column(
        "workflow_template_steps",
        sa.Column("icon_key", sa.String(length=64), nullable=False, server_default="GitBranch"),
    )
    op.execute(
        """
        UPDATE workflow_template_steps AS s
        SET icon_key = t.icon_key
        FROM workflow_templates AS t
        WHERE s.workflow_template_id = t.id
        """
    )
    op.alter_column("workflow_template_steps", "icon_key", server_default=None)


def downgrade() -> None:
    op.drop_column("workflow_template_steps", "icon_key")
