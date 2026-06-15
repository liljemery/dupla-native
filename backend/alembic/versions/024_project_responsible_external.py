"""Optional external project responsible (name, email).

Revision ID: 024_project_responsible_external
Revises: 023_step_icon_key
Create Date: 2026-05-01

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "024_project_responsible_external"
down_revision: Union[str, None] = "023_step_icon_key"


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("responsible_external_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("responsible_external_email", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "responsible_external_email")
    op.drop_column("projects", "responsible_external_name")
