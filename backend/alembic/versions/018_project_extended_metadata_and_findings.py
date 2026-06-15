"""Project extended metadata (doc alignment) and technical findings table."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "018_project_doc_alignment"
down_revision = "017_user_names"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("project_code", sa.String(length=80), nullable=True))
    op.add_column("projects", sa.Column("location_text", sa.Text(), nullable=True))
    op.add_column(
        "projects",
        sa.Column("estimated_area_sqm", sa.Numeric(precision=14, scale=2), nullable=True),
    )
    op.add_column("projects", sa.Column("floor_levels_count", sa.Integer(), nullable=True))
    op.add_column("projects", sa.Column("deadline", sa.Date(), nullable=True))
    op.add_column(
        "projects",
        sa.Column("responsible_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_projects_responsible_user_id_users",
        "projects",
        "users",
        ["responsible_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_projects_project_code", "projects", ["project_code"], unique=True)

    op.create_table(
        "project_technical_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("discipline", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_project_technical_findings_project_id",
        "project_technical_findings",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_technical_findings_project_id", table_name="project_technical_findings")
    op.drop_table("project_technical_findings")
    op.drop_index("ix_projects_project_code", table_name="projects")
    op.drop_constraint("fk_projects_responsible_user_id_users", "projects", type_="foreignkey")
    op.drop_column("projects", "responsible_user_id")
    op.drop_column("projects", "deadline")
    op.drop_column("projects", "floor_levels_count")
    op.drop_column("projects", "estimated_area_sqm")
    op.drop_column("projects", "location_text")
    op.drop_column("projects", "project_code")
