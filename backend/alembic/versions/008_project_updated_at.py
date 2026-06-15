"""projects.updated_at for last modification

Revision ID: 008_project_updated_at
Revises: 007_plan_delivery_requests
Create Date: 2026-04-18

"""

from collections.abc import Sequence
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_project_updated_at"
down_revision: Optional[str] = "007_plan_delivery_requests"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(sa.text("UPDATE projects SET updated_at = created_at"))
    op.alter_column("projects", "updated_at", nullable=False)


def downgrade() -> None:
    op.drop_column("projects", "updated_at")
