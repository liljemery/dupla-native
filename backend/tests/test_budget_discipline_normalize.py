from app.models.project_file import ProjectFile
from app.services.budget_service import _normalize_budget_discipline


def test_normalize_todas_uses_inferred_discipline() -> None:
    files = [
        ProjectFile(original_name="LAS NASAS ARQ.dwg", discipline="arquitectura"),
    ]
    assert _normalize_budget_discipline("todas", files) == "arquitectura"
