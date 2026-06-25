from app.models.project_file import ProjectFile
from app.services.budget_service import _normalize_budget_discipline


def test_normalize_todas_passes_through_to_processor() -> None:
    files = [
        ProjectFile(original_name="LAS NASAS ARQ.dwg", discipline="arquitectura"),
    ]
    assert _normalize_budget_discipline("todas", files) == "todas"
    assert _normalize_budget_discipline(None, files) == "todas"


def test_normalize_auto_infers_from_files() -> None:
    files = [
        ProjectFile(original_name="ES 01 Cimientos.dwg", discipline="estructura"),
    ]
    assert _normalize_budget_discipline("auto", files) == "estructura"
