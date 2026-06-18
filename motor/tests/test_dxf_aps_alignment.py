"""Tests for DXF model-space to APS sheet-space alignment solving."""

from __future__ import annotations

import math
import sys
from pathlib import Path

MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

from coordination.extraction.dxf_aps_alignment import (
    apply_alignment_to_bounds,
    apply_alignment_to_point,
    solve_dxf_to_aps_alignment,
    solve_dxf_to_aps_alignment_by_view,
)
from coordination.extraction.dxf_aps_matching import ApsGeometryRecord, DxfApsMatchPair
from coordination.extraction.dxf_geometry import DxfGeometryRecord


def _transform(point: tuple[float, float], *, scale: float, rotation_deg: float, translation: tuple[float, float], flip_y: bool = False) -> tuple[float, float]:
    x, y = point
    if flip_y:
        y *= -1.0
    rad = math.radians(rotation_deg)
    c, s = math.cos(rad), math.sin(rad)
    return (
        scale * (c * x - s * y) + translation[0],
        scale * (s * x + c * y) + translation[1],
    )


def _pair(handle: str, model: tuple[float, float], sheet: tuple[float, float], *, view: str = "A-1.1") -> DxfApsMatchPair:
    dxf = DxfGeometryRecord(
        handle=handle,
        layer="A-WALL",
        discipline="ARQUITECTURA",
        dxftype="LINE",
        source_ref=f"sample|{handle}",
        model_bounds=(model[0] - 0.5, model[1] - 0.5, model[0] + 0.5, model[1] + 0.5),
        model_center=model,
        geometry_quality="good",
        block_resolution_method="direct_fast",
        is_physical=True,
    )
    aps = ApsGeometryRecord(
        handle=handle,
        db_id=handle,
        layer="A-WALL",
        view_name=view,
        sheet_bounds=(0.0, 0.0, 36.0, 24.0),
        sheet_world_bounds=(sheet[0] - 0.1, sheet[1] - 0.1, sheet[0] + 0.1, sheet[1] + 0.1),
        sheet_center=sheet,
        geometry_quality="good",
        refinement="aggregate",
    )
    return DxfApsMatchPair(handle=handle, dxf=dxf, aps=aps)


def test_solve_dxf_to_aps_alignment_recovers_known_similarity() -> None:
    model_points = [(0.0, 0.0), (20.0, 0.0), (0.0, 12.0), (20.0, 12.0), (7.0, 5.0)]
    pairs = [
        _pair(f"H{i}", point, _transform(point, scale=0.5, rotation_deg=30.0, translation=(2.0, 3.0)))
        for i, point in enumerate(model_points)
    ]

    report = solve_dxf_to_aps_alignment(pairs)
    transform = report.transform

    assert transform.status == "ok"
    assert transform.n_pairs == 5
    assert transform.n_inliers == 5
    assert transform.n_outliers == 0
    assert transform.scale == pytest_approx(0.5)
    assert transform.rotation_deg == pytest_approx(30.0)
    assert transform.translation == pytest_approx_tuple((2.0, 3.0))
    assert transform.rms_error_sheet is not None and transform.rms_error_sheet < 1e-8


def test_solve_dxf_to_aps_alignment_rejects_outlier() -> None:
    model_points = [(0.0, 0.0), (20.0, 0.0), (0.0, 12.0), (20.0, 12.0), (7.0, 5.0)]
    pairs = [
        _pair(f"H{i}", point, _transform(point, scale=0.4, rotation_deg=-10.0, translation=(5.0, 1.0)))
        for i, point in enumerate(model_points)
    ]
    pairs.append(_pair("BAD", (30.0, 30.0), (100.0, 100.0)))

    report = solve_dxf_to_aps_alignment(pairs)

    assert report.transform.status == "ok"
    assert report.transform.n_inliers == 5
    assert report.transform.n_outliers == 1
    assert report.outlier_handles == ["BAD"]
    assert report.residuals_by_handle["BAD"] > 1.0


def test_solve_dxf_to_aps_alignment_recovers_flip_y() -> None:
    model_points = [(0.0, 0.0), (10.0, 0.0), (0.0, 6.0), (10.0, 6.0)]
    pairs = [
        _pair(f"H{i}", point, _transform(point, scale=0.75, rotation_deg=5.0, translation=(1.0, 20.0), flip_y=True))
        for i, point in enumerate(model_points)
    ]

    report = solve_dxf_to_aps_alignment(pairs)

    assert report.transform.status == "ok"
    assert report.transform.flip_y is True
    assert report.transform.scale == pytest_approx(0.75)


def test_solve_dxf_to_aps_alignment_by_view_groups_pairs() -> None:
    view_a = [_pair("A1", (0.0, 0.0), (1.0, 1.0), view="A"), _pair("A2", (10.0, 0.0), (11.0, 1.0), view="A"), _pair("A3", (0.0, 10.0), (1.0, 11.0), view="A")]
    view_b = [_pair("B1", (0.0, 0.0), (2.0, 2.0), view="B"), _pair("B2", (10.0, 0.0), (12.0, 2.0), view="B"), _pair("B3", (0.0, 10.0), (2.0, 12.0), view="B")]

    reports = solve_dxf_to_aps_alignment_by_view(view_a + view_b)

    assert set(reports) == {"A", "B"}
    assert reports["A"].transform.status == "ok"
    assert reports["B"].transform.status == "ok"
    assert reports["A"].view_name == "A"


def test_apply_alignment_to_point_and_bounds() -> None:
    pairs = [
        _pair("H1", (0.0, 0.0), (2.0, 3.0)),
        _pair("H2", (10.0, 0.0), (7.0, 3.0)),
        _pair("H3", (0.0, 10.0), (2.0, 8.0)),
    ]
    report = solve_dxf_to_aps_alignment(pairs)

    assert apply_alignment_to_point((4.0, 4.0), report.transform) == pytest_approx_tuple((4.0, 5.0))
    assert apply_alignment_to_bounds((0.0, 0.0, 2.0, 2.0), report.transform) == pytest_approx_tuple((2.0, 3.0, 3.0, 4.0))


def test_solve_dxf_to_aps_alignment_reports_insufficient_pairs() -> None:
    report = solve_dxf_to_aps_alignment([_pair("H1", (0.0, 0.0), (1.0, 1.0))])

    assert report.transform.status == "insufficient"
    assert report.transform.n_pairs == 1


def pytest_approx(value: float):
    import pytest

    return pytest.approx(value, abs=1e-8)


def pytest_approx_tuple(values: tuple[float, ...]):
    import pytest

    return pytest.approx(values, abs=1e-8)

