"""workflow_templates.icon_key for Lucide icon name in UI."""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020_workflow_template_icon_key"
down_revision: str | None = "019_workflow_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_templates",
        sa.Column(
            "icon_key",
            sa.String(length=64),
            nullable=False,
            server_default="GitBranch",
        ),
    )
    op.alter_column("workflow_templates", "icon_key", server_default=None)


def downgrade() -> None:
    op.drop_column("workflow_templates", "icon_key")
