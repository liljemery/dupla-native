"""FOSS-only plan geometry audit from DXF inputs (no APS viewer)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from coordination.core.models_25d import Discipline
from coordination.extraction.dxf_geometry import extract_dxf_geometry


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _footprint_from_bounds(bounds: tuple[float, float, float, float]) -> list[list[float]]:
    xmin, ymin, xmax, ymax = bounds
    return [
        [round(float(xmin), 6), round(float(ymin), 6)],
        [round(float(xmax), 6), round(float(ymin), 6)],
        [round(float(xmax), 6), round(float(ymax), 6)],
        [round(float(xmin), 6), round(float(ymax), 6)],
    ]


def discover_dxf_only_sources(
    *,
    inputs_dir: Path,
    discipline_for_path: Any | None = None,
) -> list[tuple[Path, Discipline | str, str]]:
    """DXF inputs for FOSS-only geometry audit."""
    inputs_dir = Path(inputs_dir)
    if not inputs_dir.is_dir():
        return []
    out: list[tuple[Path, Discipline | str, str]] = []
    for dxf_path in sorted(inputs_dir.rglob("*.dxf")):
        discipline: Discipline | str = Discipline.ARCH
        if discipline_for_path is not None:
            resolved = discipline_for_path(dxf_path)
            if resolved:
                discipline = resolved
        out.append((dxf_path, discipline, dxf_path.name))
    return out


def build_dxf_only_audit_artifacts(
    sources: list[tuple[Path, Discipline | str, str]],
    output_dir: Path,
) -> dict[str, Any]:
    """Build plan geometry + audit from ezdxf extraction only."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, Any]] = {}
    source_summaries: list[dict[str, Any]] = []

    for dxf_path, discipline, file_name in sources:
        extraction = extract_dxf_geometry(dxf_path, discipline, include_non_physical=True)
        physical = [record for record in extraction.records if record.is_physical]
        elements: list[dict[str, Any]] = []
        for record in physical:
            if not record.model_bounds:
                continue
            elements.append(
                {
                    "handle": record.handle,
                    "layer": record.layer,
                    "dxftype": record.dxftype,
                    "footprint": _footprint_from_bounds(record.model_bounds),
                    "center": [round(float(record.model_center[0]), 6), round(float(record.model_center[1]), 6)],
                    "geometry_source": "dxf_ezdxf_transformed",
                    "geometry_quality": record.geometry_quality,
                    "coordinate_unit": record.coordinate_unit,
                }
            )
        discipline_value = discipline.value if isinstance(discipline, Discipline) else str(discipline)
        files[file_name] = {
            "discipline": discipline_value,
            "coordinate_unit": "model_meters",
            "element_count": len(elements),
            "elements": elements,
            "geometry_source_counts": {"dxf_ezdxf_transformed": len(elements)},
        }
        source_summaries.append(
            {
                "dxf_path": str(dxf_path),
                "file_name": file_name,
                "entity_count": len(extraction.records),
                "physical_count": len(physical),
                "insunits": extraction.insunits,
            }
        )

    plan_geometry_path = output_dir / "plan_geometry.dxf_only.json"
    manifest_path = output_dir / "hybrid_geometry_manifest.json"
    audit_path = output_dir / "hybrid_geometry_audit.json"
    audit_markdown_path = output_dir / "hybrid_geometry_audit.md"
    plan_payload = {
        "schema_version": "dxf_only_plan_geometry.v1",
        "coordinate_unit": "model_meters",
        "files": dict(sorted(files.items())),
    }
    _write_json(plan_geometry_path, plan_payload)
    manifest_payload = {
        "output_dir": str(output_dir),
        "plan_geometry_path": str(plan_geometry_path),
        "mode": "dxf_only",
        "sources": source_summaries,
    }
    audit_payload = {
        "status": "ok" if files else "missing",
        "mode": "dxf_only",
        "summary": {
            "source_count": len(sources),
            "file_count": len(files),
            "total_elements": sum(entry.get("element_count", 0) for entry in files.values()),
        },
        "issues": [] if files else [{"severity": "fail", "code": "no_dxf_sources", "message": "No DXF sources found"}],
    }
    _write_json(manifest_path, manifest_payload)
    _write_json(audit_path, audit_payload)
    audit_markdown_path.write_text(
        "# DXF-only geometry audit\n\n"
        f"- Sources: {len(sources)}\n"
        f"- Files: {len(files)}\n"
        f"- Status: {audit_payload['status']}\n",
        encoding="utf-8",
    )
    return {
        "output_dir": str(output_dir),
        "plan_geometry_path": str(plan_geometry_path),
        "manifest_path": str(manifest_path),
        "audit_path": str(audit_path),
        "audit_markdown_path": str(audit_markdown_path),
        "audit": {"status": audit_payload["status"], "summary": audit_payload["summary"]},
        "mode": "dxf_only",
    }
