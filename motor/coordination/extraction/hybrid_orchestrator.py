"""Orchestrate DXF + APS Viewer artifacts into hybrid plan geometry JSON."""

from __future__ import annotations

import argparse
import base64
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from coordination.core.models_25d import Discipline
from coordination.extraction.dxf_aps_alignment import solve_dxf_to_aps_alignment_by_view
from coordination.extraction.dxf_aps_matching import build_dxf_aps_match_report
from coordination.extraction.dxf_geometry import extract_dxf_geometry
from coordination.extraction.hybrid_geometry import HybridGeometryBuildReport, HybridGeometryRecord, build_hybrid_geometry
from coordination.extraction.hybrid_geometry_audit import audit_hybrid_geometry_manifest, render_hybrid_geometry_audit_markdown


@dataclass(frozen=True)
class HybridSourceInput:
    dxf_path: Path
    viewer_json_path: Path
    discipline: Discipline | str
    file_name: str | None = None
    label: str | None = None


@dataclass
class HybridArtifactResult:
    source: HybridSourceInput
    artifact_prefix: str
    dxf_geometry_path: Path
    match_report_path: Path
    alignment_report_path: Path
    hybrid_records_path: Path
    hybrid_report: HybridGeometryBuildReport
    match_summary: dict[str, Any]
    alignment_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": {
                "dxf_path": str(self.source.dxf_path),
                "viewer_json_path": str(self.source.viewer_json_path),
                "discipline": self.source.discipline.value if isinstance(self.source.discipline, Discipline) else str(self.source.discipline),
                "file_name": self.source.file_name,
                "label": self.source.label,
            },
            "artifact_prefix": self.artifact_prefix,
            "paths": {
                "dxf_geometry": str(self.dxf_geometry_path),
                "match_report": str(self.match_report_path),
                "alignment_report": str(self.alignment_report_path),
                "hybrid_records": str(self.hybrid_records_path),
            },
            "match_summary": self.match_summary,
            "alignment_summary": self.alignment_summary,
            "hybrid_summary": {
                "record_count": len(self.hybrid_report.records),
                "source_counts": self.hybrid_report.source_counts,
                "quality_counts": self.hybrid_report.quality_counts,
                "skipped": self.hybrid_report.skipped,
            },
        }


@dataclass
class HybridArtifactBundle:
    output_dir: Path
    plan_geometry_path: Path
    manifest_path: Path
    audit_path: Path
    audit_markdown_path: Path
    audit: dict[str, Any] = field(default_factory=dict)
    results: list[HybridArtifactResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": str(self.output_dir),
            "plan_geometry_path": str(self.plan_geometry_path),
            "manifest_path": str(self.manifest_path),
            "audit_path": str(self.audit_path),
            "audit_markdown_path": str(self.audit_markdown_path),
            "audit": {
                "status": self.audit.get("status"),
                "summary": self.audit.get("summary"),
            } if self.audit else {},
            "results": [result.to_dict() for result in self.results],
        }


def _safe_prefix(source: HybridSourceInput, index: int) -> str:
    raw = source.label or source.file_name or source.dxf_path.stem or f"source_{index}"
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    return text or f"source_{index}"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _decode_aps_urn(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("urn:"):
        return text
    pad = "=" * (-len(text) % 4)
    try:
        return base64.b64decode(text + pad).decode("utf-8", errors="ignore")
    except Exception:
        return text


def _viewer_haystack(path: Path) -> str:
    try:
        payload = _read_json(path)
    except Exception:
        return path.name.upper()
    urn = str(payload.get("urn") or "")
    cache_metadata = payload.get("cache_metadata") if isinstance(payload.get("cache_metadata"), dict) else {}
    source_urn = str(cache_metadata.get("urn") or "")
    decoded = " ".join(_decode_aps_urn(item) for item in (urn, source_urn))
    return f"{path.name} {decoded}".upper()


def _viewer_matches_dxf(dxf_path: Path, viewer_path: Path) -> bool:
    stem = dxf_path.stem.upper()
    name = dxf_path.name.upper()
    haystack = _viewer_haystack(viewer_path)
    compact_stem = re.sub(r"[^A-Z0-9]+", "", stem)
    compact_haystack = re.sub(r"[^A-Z0-9]+", "", haystack)
    return name in haystack or stem in haystack or (compact_stem and compact_stem in compact_haystack)


def discover_hybrid_sources(
    *,
    inputs_dir: Path,
    cache_dir: Path,
    discipline_for_path: Any | None = None,
) -> list[HybridSourceInput]:
    """Find DXF inputs with matching APS Viewer dumps in a coordination run."""
    inputs_dir = Path(inputs_dir)
    cache_dir = Path(cache_dir)
    if not inputs_dir.is_dir() or not cache_dir.is_dir():
        return []
    viewer_paths = sorted(cache_dir.glob("*.viewer.json"))
    sources: list[HybridSourceInput] = []
    for dxf_path in sorted(inputs_dir.rglob("*.dxf")):
        viewer_path = next((candidate for candidate in viewer_paths if _viewer_matches_dxf(dxf_path, candidate)), None)
        if viewer_path is None:
            continue
        discipline: Discipline | str = "ARQUITECTURA"
        if discipline_for_path is not None:
            resolved = discipline_for_path(dxf_path)
            if resolved:
                discipline = resolved
        sources.append(
            HybridSourceInput(
                dxf_path=dxf_path,
                viewer_json_path=viewer_path,
                discipline=discipline,
                file_name=dxf_path.name,
                label=dxf_path.stem,
            )
        )
    return sources


def _footprint_from_bounds(bounds: tuple[float, float, float, float]) -> list[list[float]]:
    min_x, min_y, max_x, max_y = bounds
    return [
        [round(float(min_x), 6), round(float(min_y), 6)],
        [round(float(max_x), 6), round(float(min_y), 6)],
        [round(float(max_x), 6), round(float(max_y), 6)],
        [round(float(min_x), 6), round(float(max_y), 6)],
    ]


def _record_to_plan_element(record: HybridGeometryRecord) -> dict[str, Any]:
    payload = {
        "handle": record.handle,
        "dbId": record.db_id,
        "source_ref": record.source_ref,
        "discipline": record.discipline,
        "layer": record.layer,
        "dxftype": record.dxftype,
        "footprint": _footprint_from_bounds(record.sheet_bounds),
        "center": [round(float(record.sheet_center[0]), 6), round(float(record.sheet_center[1]), 6)],
        "coordinate_unit": record.coordinate_unit,
        "geometry_quality": record.geometry_quality,
        "geometry_source": record.geometry_source,
        "world_bounds": [round(float(v), 6) for v in record.sheet_bounds],
        "model_bounds": [round(float(v), 6) for v in record.model_bounds] if record.model_bounds is not None else None,
        "model_center": [round(float(v), 6) for v in record.model_center] if record.model_center is not None else None,
        "aps_sheet_bounds": [round(float(v), 6) for v in record.aps_sheet_bounds] if record.aps_sheet_bounds is not None else None,
        "transform_status": record.transform_status,
        "sheet_or_view_name": record.view_name,
    }
    return {key: value for key, value in payload.items() if value not in (None, "", [])}


def build_plan_geometry_payload(results: list[HybridArtifactResult]) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for result in results:
        file_name = result.source.file_name or result.source.dxf_path.name
        discipline = result.source.discipline.value if isinstance(result.source.discipline, Discipline) else str(result.source.discipline)
        entry = files.setdefault(file_name, {"discipline": discipline, "coordinate_unit": "sheet_paper_units", "elements": []})
        entry["elements"].extend(_record_to_plan_element(record) for record in result.hybrid_report.records)

    for entry in files.values():
        elements = entry["elements"]
        xs = [point[0] for element in elements for point in element.get("footprint", [])]
        ys = [point[1] for element in elements for point in element.get("footprint", [])]
        entry["element_count"] = len(elements)
        entry["extents_by_unit"] = {
            "sheet_paper_units": [min(xs), min(ys), max(xs), max(ys)]
        } if xs and ys else {}
        source_counts: dict[str, int] = {}
        quality_counts: dict[str, int] = {}
        for element in elements:
            source = str(element.get("geometry_source") or "unknown")
            quality = str(element.get("geometry_quality") or "unknown")
            source_counts[source] = source_counts.get(source, 0) + 1
            quality_counts[quality] = quality_counts.get(quality, 0) + 1
        entry["geometry_source_counts"] = dict(sorted(source_counts.items()))
        entry["geometry_quality_counts"] = dict(sorted(quality_counts.items()))

    return {
        "schema_version": "hybrid_plan_geometry.v1",
        "coordinate_unit": "sheet_paper_units",
        "files": dict(sorted(files.items())),
    }


def build_hybrid_artifacts(
    sources: list[HybridSourceInput],
    output_dir: Path,
    *,
    include_aps_fallback: bool = True,
) -> HybridArtifactBundle:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[HybridArtifactResult] = []

    for index, source in enumerate(sources, start=1):
        prefix = _safe_prefix(source, index)
        viewer_dump = _read_json(source.viewer_json_path)
        dxf_geometry = extract_dxf_geometry(source.dxf_path, source.discipline, include_non_physical=True)
        match_report = build_dxf_aps_match_report(dxf_geometry, viewer_dump)
        alignments_by_view = solve_dxf_to_aps_alignment_by_view(match_report.pairs)
        hybrid_report = build_hybrid_geometry(match_report, alignments_by_view, include_aps_fallback=include_aps_fallback)

        dxf_geometry_path = output_dir / f"{prefix}.dxf_geometry.json"
        match_report_path = output_dir / f"{prefix}.dxf_aps_match_report.json"
        alignment_report_path = output_dir / f"{prefix}.dxf_aps_alignment_report.json"
        hybrid_records_path = output_dir / f"{prefix}.hybrid_records.json"

        alignment_payload = {view: report.to_dict() for view, report in alignments_by_view.items()}
        _write_json(dxf_geometry_path, dxf_geometry.to_dict())
        _write_json(match_report_path, match_report.to_dict())
        _write_json(alignment_report_path, alignment_payload)
        _write_json(hybrid_records_path, hybrid_report.to_dict())

        results.append(
            HybridArtifactResult(
                source=source,
                artifact_prefix=prefix,
                dxf_geometry_path=dxf_geometry_path,
                match_report_path=match_report_path,
                alignment_report_path=alignment_report_path,
                hybrid_records_path=hybrid_records_path,
                hybrid_report=hybrid_report,
                match_summary={
                    "pair_count": len(match_report.pairs),
                    "pairs_by_view": match_report.pairs_by_view,
                    "rejected": match_report.rejected,
                },
                alignment_summary={
                    view: {
                        "status": report.transform.status,
                        "n_pairs": report.transform.n_pairs,
                        "n_inliers": report.transform.n_inliers,
                        "n_outliers": report.transform.n_outliers,
                        "rms_error_sheet": report.transform.rms_error_sheet,
                        "max_error_sheet": report.transform.max_error_sheet,
                    }
                    for view, report in alignments_by_view.items()
                },
            )
        )

    plan_geometry_path = output_dir / "plan_geometry.hybrid.json"
    manifest_path = output_dir / "hybrid_geometry_manifest.json"
    audit_path = output_dir / "hybrid_geometry_audit.json"
    audit_markdown_path = output_dir / "hybrid_geometry_audit.md"
    _write_json(plan_geometry_path, build_plan_geometry_payload(results))
    bundle = HybridArtifactBundle(
        output_dir=output_dir,
        plan_geometry_path=plan_geometry_path,
        manifest_path=manifest_path,
        audit_path=audit_path,
        audit_markdown_path=audit_markdown_path,
        results=results,
    )
    manifest_payload = bundle.to_dict()
    audit_payload = audit_hybrid_geometry_manifest(manifest_payload)
    audit_payload["manifest_path"] = str(manifest_path)
    bundle.audit = audit_payload
    _write_json(audit_path, audit_payload)
    audit_markdown_path.write_text(render_hybrid_geometry_audit_markdown(audit_payload), encoding="utf-8")
    _write_json(manifest_path, bundle.to_dict())
    return bundle


def _parse_source(value: str) -> HybridSourceInput:
    parts = value.split("|")
    if len(parts) < 3:
        raise argparse.ArgumentTypeError("source must be DXF|VIEWER_JSON|DISCIPLINE[|FILE_NAME][|LABEL]")
    return HybridSourceInput(
        dxf_path=Path(parts[0]),
        viewer_json_path=Path(parts[1]),
        discipline=parts[2],
        file_name=parts[3] if len(parts) >= 4 and parts[3] else None,
        label=parts[4] if len(parts) >= 5 and parts[4] else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build hybrid DXF/APS plan geometry artifacts")
    parser.add_argument("--source", action="append", type=_parse_source, required=True, help="DXF|VIEWER_JSON|DISCIPLINE[|FILE_NAME][|LABEL]")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--no-aps-fallback", action="store_true")
    args = parser.parse_args(argv)

    bundle = build_hybrid_artifacts(
        args.source,
        args.output_dir,
        include_aps_fallback=not args.no_aps_fallback,
    )
    print(json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
