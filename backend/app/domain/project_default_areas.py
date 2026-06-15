from __future__ import annotations

from app.domain.project_kind import ProjectKind

ESTIMATED_CONSTRUCTION_AREA_NAME = "Área Estimada de Construcción"
ESTIMATED_SALES_AREA_NAME = "Área Estimada de Ventas"


def default_area_names_for_project_kind(project_kind: str) -> list[str]:
    names = [ESTIMATED_CONSTRUCTION_AREA_NAME]
    if project_kind == ProjectKind.DEVELOPMENT.value:
        names.append(ESTIMATED_SALES_AREA_NAME)
    return names
