"""plan delivery requests (GA-FO-03)

Revision ID: 007_plan_delivery_requests
Revises: 006_project_members
Create Date: 2026-04-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007_plan_delivery_requests"
down_revision: Union[str, None] = "006_project_members"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plan_delivery_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("request_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("days_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "sequence_number", name="uq_plan_delivery_project_seq"),
    )
    op.create_index("ix_plan_delivery_requests_project_id", "plan_delivery_requests", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_plan_delivery_requests_project_id", table_name="plan_delivery_requests")
    op.drop_table("plan_delivery_requests")
