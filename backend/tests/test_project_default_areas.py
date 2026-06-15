"""Default estimated areas on project creation."""

from app.domain.project_default_areas import (
    ESTIMATED_CONSTRUCTION_AREA_NAME,
    ESTIMATED_SALES_AREA_NAME,
    default_area_names_for_project_kind,
)
from app.domain.project_kind import ProjectKind


def test_default_areas_client_only_construction():
    names = default_area_names_for_project_kind(ProjectKind.CLIENT.value)
    assert names == [ESTIMATED_CONSTRUCTION_AREA_NAME]


def test_default_areas_development_includes_sales():
    names = default_area_names_for_project_kind(ProjectKind.DEVELOPMENT.value)
    assert names == [ESTIMATED_CONSTRUCTION_AREA_NAME, ESTIMATED_SALES_AREA_NAME]


def test_default_areas_tender_only_construction():
    names = default_area_names_for_project_kind(ProjectKind.TENDER.value)
    assert names == [ESTIMATED_CONSTRUCTION_AREA_NAME]
