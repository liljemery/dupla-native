"""Add users.first_name and users.last_name."""

from alembic import op
import sqlalchemy as sa

revision = "017_user_names"
down_revision = "016_workflow_complete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("first_name", sa.String(length=120), nullable=False, server_default=""),
    )
    op.add_column(
        "users",
        sa.Column("last_name", sa.String(length=120), nullable=False, server_default=""),
    )
    op.alter_column("users", "first_name", server_default=None)
    op.alter_column("users", "last_name", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
