"""Map FILES_INGESTED -> ARCHITECTURE_REVIEW; support COMPLETE phase."""

from alembic import op

revision = "016_workflow_complete"
down_revision = "015_project_file_folders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE projects
        SET workflow_phase = 'ARCHITECTURE_REVIEW'
        WHERE workflow_phase = 'FILES_INGESTED'
        """
    )


def downgrade() -> None:
    # Cannot reliably restore FILES_INGESTED; no-op for phase values.
    pass
