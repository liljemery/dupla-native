"""Mark project row as modified (activity timestamp)."""

from datetime import datetime, timezone

from app.models.project import Project


def touch_project_updated_at(project: Project) -> None:
    project.updated_at = datetime.now(timezone.utc)
