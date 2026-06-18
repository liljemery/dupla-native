"""
(P3.9) Budget validation — triangulación, plausibilidad física, sanity $/m².
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from core.schemas import BudgetLine, ProjectContext, QuantityTakeoff


@dataclass
class BudgetValidationIssue:
    severity: str  # OK | WARNING | BLOCKED
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class BudgetValidationReport:
    issues: list[BudgetValidationIssue] = field(default_factory=list)
    ok_count: int = 0
    warning_count: int = 0
    blocked_count: int = 0
    benchmarks: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok_count": self.ok_count,
            "warning_count": self.warning_count,
            "blocked_count": self.blocked_count,
            "benchmarks": self.benchmarks,
            "issues": [
                {
                    "severity": i.severity,
                    "code": i.code,
                    "message": i.message,
                    "context": i.context,
                }
                for i in self.issues
            ],
        }


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _sum_takeoff(takeoffs: list[QuantityTakeoff], item_type: str) -> float:
    return sum(t.quantity for t in takeoffs if t.item_type == item_type)


def _line_total(lines: list[BudgetLine]) -> float:
    total = 0.0
    for line in lines:
        if line.unit_price is None:
            continue
        total += float(line.quantity) * float(line.unit_price)
    return total


def run_budget_validation(
    lines: list[BudgetLine],
    takeoffs: list[QuantityTakeoff],
    *,
    bc3_catalog: dict[str, Any] | None = None,
    context: ProjectContext | None = None,
) -> BudgetValidationReport:
    report = BudgetValidationReport()
    discipline = ""
    if context and context.metadata:
        discipline = str(context.metadata.get("discipline_id") or "")

    floor_area = _sum_takeoff(takeoffs, "floor_area")
    wall_area = _sum_takeoff(takeoffs, "wall_net_area")
    door_count = _sum_takeoff(takeoffs, "door_count")
    window_count = _sum_takeoff(takeoffs, "window_count")

    # Triangulation: wall perimeter proxy vs floor area
    if floor_area > 0 and wall_area > 0:
        ratio = wall_area / floor_area
        if ratio < 0.3 or ratio > 8.0:
            report.issues.append(BudgetValidationIssue(
                severity="WARNING",
                code="wall_floor_ratio",
                message=f"Relación muro/piso {ratio:.2f} fuera de rango típico (0.3–8).",
                context={"wall_area_m2": wall_area, "floor_area_m2": floor_area, "ratio": round(ratio, 3)},
            ))
        else:
            report.ok_count += 1

    # Count plausibility vs area
    if floor_area > 0:
        doors_per_100m2 = door_count / floor_area * 100
        if doors_per_100m2 > 15:
            report.issues.append(BudgetValidationIssue(
                severity="WARNING",
                code="door_density_high",
                message=f"Densidad de puertas alta: {doors_per_100m2:.1f} ud/100m².",
                context={"door_count": door_count, "floor_area_m2": floor_area},
            ))
        elif door_count > 0:
            report.ok_count += 1

    # Physical plausibility: negative or zero quantities in budget lines
    for line in lines:
        if line.quantity <= 0:
            report.issues.append(BudgetValidationIssue(
                severity="BLOCKED",
                code="zero_quantity_line",
                message=f"Línea con cantidad <= 0: {line.summary[:60]}",
                context={"code": line.code, "quantity": line.quantity},
            ))

    # $/m² benchmark (arquitectura / estructura only)
    total_cost = _line_total(lines)
    bench_min = _env_float("DUPLA_BENCHMARK_MIN_USD_M2", 400.0)
    bench_max = _env_float("DUPLA_BENCHMARK_MAX_USD_M2", 3500.0)
    if floor_area > 50 and total_cost > 0 and discipline in {"arquitectura", "estructura", "todas"}:
        usd_m2 = total_cost / floor_area
        report.benchmarks = {
            "total_cost": round(total_cost, 2),
            "floor_area_m2": round(floor_area, 2),
            "cost_per_m2": round(usd_m2, 2),
            "benchmark_min": bench_min,
            "benchmark_max": bench_max,
        }
        if usd_m2 < bench_min or usd_m2 > bench_max:
            report.issues.append(BudgetValidationIssue(
                severity="WARNING",
                code="cost_per_m2_outlier",
                message=f"Costo {usd_m2:.0f}/m² fuera de benchmark ({bench_min:.0f}–{bench_max:.0f}).",
                context=report.benchmarks,
            ))
        else:
            report.ok_count += 1

    for issue in report.issues:
        if issue.severity == "WARNING":
            report.warning_count += 1
        elif issue.severity == "BLOCKED":
            report.blocked_count += 1

    return report
