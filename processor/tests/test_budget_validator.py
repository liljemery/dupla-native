"""Tests for P3.9 budget validation."""

from __future__ import annotations

import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


def _tk(item_type: str, qty: float):
    from core.schemas import QuantityTakeoff, QuantityTrace

    return QuantityTakeoff(
        item_key=f"{item_type}-t",
        item_type=item_type,
        unit="m2" if "area" in item_type else "ud",
        quantity=qty,
        formula="",
        inputs={},
        trace=QuantityTrace(),
    )


def _line(qty: float, price: float, summary: str = "test"):
    from core.schemas import BudgetLine

    return BudgetLine(
        line_id="L1",
        takeoff_key="t1",
        chapter_id="c1",
        code="01.001",
        summary=summary,
        quantity=qty,
        unit_price=price,
        unit="m2",
    )


def test_wall_floor_ratio_warning():
    from validation.budget_validator import run_budget_validation

    takeoffs = [_tk("floor_area", 100), _tk("wall_net_area", 900)]
    report = run_budget_validation([_line(100, 10)], takeoffs)
    codes = [i.code for i in report.issues]
    assert "wall_floor_ratio" in codes


def test_zero_quantity_blocked():
    from validation.budget_validator import run_budget_validation

    report = run_budget_validation([_line(0, 10)], [])
    assert report.blocked_count >= 1
    assert any(i.code == "zero_quantity_line" for i in report.issues)


def test_cost_per_m2_benchmark():
    from core.schemas import ProjectContext
    from validation.budget_validator import run_budget_validation

    ctx = ProjectContext(project_id="p", metadata={"discipline_id": "arquitectura"})
    takeoffs = [_tk("floor_area", 200)]
    lines = [_line(200, 5000)]  # 5000/m2 — outlier
    report = run_budget_validation(lines, takeoffs, context=ctx)
    assert any(i.code == "cost_per_m2_outlier" for i in report.issues)
