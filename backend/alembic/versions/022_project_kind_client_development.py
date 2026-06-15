"""Replace RESIDENTIAL with CLIENT; add DEVELOPMENT as allowed kind

Revision ID: 022_project_kind_v2
Revises: 021_dupla_std_template
Create Date: 2026-05-01

"""

from typing import Union

from alembic import op

revision: str = "022_project_kind_v2"
down_revision: Union[str, None] = "021_dupla_std_template"


def upgrade() -> None:
    op.execute(
        "UPDATE projects SET project_kind = 'CLIENT' WHERE project_kind = 'RESIDENTIAL'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE projects SET project_kind = 'RESIDENTIAL' WHERE project_kind IN ('CLIENT', 'DEVELOPMENT')"
    )
