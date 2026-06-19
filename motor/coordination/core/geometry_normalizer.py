"""Phase-1 geometry normalization: units + cleanup + provenance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from coordination.core.geometry_cleaner import GeometryCleanupResult, clean_geometry
from coordination.core.units import (
    UnitInference,
    UnitReconciliation,
    infer_units_from_geometry,
    reconcile_units,
)


@dataclass(frozen=True)
class GeometryNormalizationResult:
    geometry: list[dict[str, Any]]
    main_geometry: list[dict[str, Any]]
    stray_geometry: list[dict[str, Any]]
    unit_inference: UnitInference
    unit_reconciliation: UnitReconciliation
    cleanup: GeometryCleanupResult
    report: dict[str, Any]


def normalize(
    discipline: str,
    geometry: list[dict[str, Any]],
    *,
    declared_insunits: int | None = None,
    measurement: int | None = None,
    dimensions: list[dict[str, Any]] | None = None,
    geometry_hints: list[dict[str, Any]] | None = None,
    cleanup_method: str = "percentile",
) -> GeometryNormalizationResult:
    """Normalize extracted CAD geometry to meters and separate stray geometry.

    This is intentionally a thin orchestrator over the promoted POC pieces. Input rows
    may carry ``model_bounds``/``model_center`` or ``bounds``/``center`` in native
    drawing units. Output rows preserve the original values and add normalized meter
    values under ``model_bounds_m`` and ``model_center_m``.
    """
    rows = [dict(row) for row in geometry or []]
    inference = infer_units_from_geometry(rows, dimensions=dimensions, geometry_hints=geometry_hints)
    reconciliation = reconcile_units(
        declared_insunits,
        inference,
        discipline=discipline,
        measurement=measurement,
    )
    factor = reconciliation.factor_to_meters
    normalized = [_normalize_row(row, factor) for row in rows]
    cleanup = clean_geometry(normalized, method=cleanup_method)
    main_ids = {id(row) for row in cleanup.main_geometry}
    output: list[dict[str, Any]] = []
    for row in normalized:
        status = "main" if id(row) in main_ids else "stray"
        row["normalization_status"] = status
        row["coordinate_unit"] = "model_meters"
        row["unit_factor_to_meters"] = factor
        output.append(row)

    report = {
        "discipline": discipline,
        "declared_insunits": declared_insunits,
        "declared_factor_to_meters": reconciliation.declared_factor_to_meters,
        "inferred_factor_to_meters": inference.factor_to_meters,
        "inferred_unit": inference.unit_label,
        "final_factor_to_meters": factor,
        "unit_source": reconciliation.source,
        "outline_before": inference.outline_before,
        "outline_after": inference.outline_after,
        "unit_warning": reconciliation.warning,
        "stray_count": cleanup.stray_count,
        "cleaned_centroid": cleanup.cleaned_centroid,
        "cleaned_outline": cleanup.cleaned_outline,
        "cleanup_method": cleanup.method,
        "cleanup_diagnostics": cleanup.diagnostics,
    }
    return GeometryNormalizationResult(
        geometry=output,
        main_geometry=cleanup.main_geometry,
        stray_geometry=cleanup.stray_geometry,
        unit_inference=inference,
        unit_reconciliation=reconciliation,
        cleanup=cleanup,
        report=report,
    )


def _normalize_row(row: dict[str, Any], factor_to_meters: float) -> dict[str, Any]:
    normalized = dict(row)
    bounds = row.get("model_bounds") or row.get("bounds") or row.get("bbox")
    center = row.get("model_center") or row.get("center")
    if bounds and len(bounds) >= 4:
        try:
            normalized.setdefault("raw_model_bounds", list(bounds))
            normalized["model_bounds_m"] = [
                float(bounds[0]) * factor_to_meters,
                float(bounds[1]) * factor_to_meters,
                float(bounds[2]) * factor_to_meters,
                float(bounds[3]) * factor_to_meters,
            ]
            normalized["model_bounds"] = list(normalized["model_bounds_m"])
        except Exception:
            pass
    if center and len(center) >= 2:
        try:
            normalized.setdefault("raw_model_center", list(center))
            normalized["model_center_m"] = [
                float(center[0]) * factor_to_meters,
                float(center[1]) * factor_to_meters,
            ]
            normalized["model_center"] = list(normalized["model_center_m"])
        except Exception:
            pass
    elif normalized.get("model_bounds_m"):
        b = normalized["model_bounds_m"]
        normalized["model_center_m"] = [(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0]
        normalized["model_center"] = list(normalized["model_center_m"])
    return normalized
