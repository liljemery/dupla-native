"""Tests for hybrid geometry artifact orchestration."""

from __future__ import annotations

import json
import math
import base64
import sys
from pathlib import Path

import ezdxf

MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

from coordination.core.models_25d import Discipline
from coordination.extraction.hybrid_geometry import (
    APS_FRAGMENT_FALLBACK_GEOMETRY_SOURCE,
    DXF_TRANSFORMED_GEOMETRY_SOURCE,
)
from coordination.extraction.hybrid_orchestrator import HybridSourceInput, build_hybrid_artifacts, discover_hybrid_sources, main


def _sheet_xy(model_xy: tuple[float, float]) -> tuple[float, float]:
    scale = 0.5
    rotation = math.radians(8.0)
    c, s = math.cos(rotation), math.sin(rotation)
    x, y = model_xy
    return (
        scale * (c * x - s * y) + 2.0,
        scale * (s * x + c * y) + 3.0,
    )


def _write_dxf(path: Path) -> dict[str, tuple[float, float]]:
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6
    doc.layers.add("A-WALL")
    doc.layers.add("TEXTOS")
    msp = doc.modelspace()
    entities = [
        msp.add_line((0.0, 0.0), (2.0, 2.0), dxfattribs={"layer": "A-WALL"}),
        msp.add_line((20.0, 0.0), (22.0, 2.0), dxfattribs={"layer": "A-WALL"}),
        msp.add_line((0.0, 12.0), (2.0, 14.0), dxfattribs={"layer": "A-WALL"}),
        msp.add_line((20.0, 12.0), (22.0, 14.0), dxfattribs={"layer": "A-WALL"}),
    ]
    note = msp.add_text("annotation", dxfattribs={"layer": "TEXTOS"})
    note.set_placement((50.0, 50.0))
    doc.saveas(path)

    centers: dict[str, tuple[float, float]] = {}
    for entity in entities:
        start = entity.dxf.start
        end = entity.dxf.end
        centers[str(entity.dxf.handle).upper()] = ((float(start.x) + float(end.x)) / 2.0, (float(start.y) + float(end.y)) / 2.0)
    centers[str(note.dxf.handle).upper()] = (50.0, 50.0)
    return centers


def _write_viewer(path: Path, centers: dict[str, tuple[float, float]]) -> None:
    objects = []
    for index, (handle, center) in enumerate(centers.items(), start=1):
        layer = "TEXTOS" if center == (50.0, 50.0) else "A-WALL"
        sx, sy = _sheet_xy(center)
        objects.append(
            {
                "handle": handle,
                "dbId": index,
                "layer": layer,
                "world_bounds": [sx - 0.1, sy - 0.1, sx + 0.1, sy + 0.1],
            }
        )
    objects.append({"handle": "APS_ONLY", "dbId": 999, "layer": "A-WALL", "world_bounds": [20.0, 20.0, 21.0, 21.0]})
    payload = {"views": [{"name": "A-1.1", "sheet_bounds": [0.0, 0.0, 36.0, 24.0], "objects": objects}]}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_hybrid_artifacts_writes_manifest_and_plan_geometry(tmp_path: Path) -> None:
    dxf_path = tmp_path / "arq.dxf"
    viewer_path = tmp_path / "arq.viewer.json"
    centers = _write_dxf(dxf_path)
    _write_viewer(viewer_path, centers)
    output_dir = tmp_path / "out"

    bundle = build_hybrid_artifacts(
        [
            HybridSourceInput(
                dxf_path=dxf_path,
                viewer_json_path=viewer_path,
                discipline=Discipline.ARCH,
                file_name="ARQ.dwg",
                label="arq",
            )
        ],
        output_dir,
    )

    assert bundle.plan_geometry_path.is_file()
    assert bundle.manifest_path.is_file()
    assert bundle.audit_path.is_file()
    assert bundle.audit_markdown_path.is_file()
    assert bundle.audit["status"] == "warn"
    result = bundle.results[0]
    assert result.dxf_geometry_path.is_file()
    assert result.match_report_path.is_file()
    assert result.alignment_report_path.is_file()
    assert result.hybrid_records_path.is_file()
    assert result.match_summary["pair_count"] == 4
    assert result.alignment_summary["A-1.1"]["status"] == "ok"

    plan = json.loads(bundle.plan_geometry_path.read_text(encoding="utf-8"))
    entry = plan["files"]["ARQ.dwg"]
    assert plan["schema_version"] == "hybrid_plan_geometry.v1"
    assert entry["coordinate_unit"] == "sheet_paper_units"
    assert entry["geometry_source_counts"][DXF_TRANSFORMED_GEOMETRY_SOURCE] == 4
    assert entry["geometry_source_counts"][APS_FRAGMENT_FALLBACK_GEOMETRY_SOURCE] == 1
    assert entry["element_count"] == 5

    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    assert manifest["audit_path"].endswith("hybrid_geometry_audit.json")
    assert manifest["audit_markdown_path"].endswith("hybrid_geometry_audit.md")
    assert manifest["audit"]["status"] == "warn"


def test_build_hybrid_artifacts_can_disable_aps_fallback(tmp_path: Path) -> None:
    dxf_path = tmp_path / "arq.dxf"
    viewer_path = tmp_path / "arq.viewer.json"
    centers = _write_dxf(dxf_path)
    _write_viewer(viewer_path, centers)

    bundle = build_hybrid_artifacts(
        [HybridSourceInput(dxf_path=dxf_path, viewer_json_path=viewer_path, discipline="ARQUITECTURA", file_name="ARQ.dwg")],
        tmp_path / "out",
        include_aps_fallback=False,
    )

    plan = json.loads(bundle.plan_geometry_path.read_text(encoding="utf-8"))
    entry = plan["files"]["ARQ.dwg"]
    assert entry["geometry_source_counts"] == {DXF_TRANSFORMED_GEOMETRY_SOURCE: 4}
    assert entry["element_count"] == 4


def test_hybrid_orchestrator_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    dxf_path = tmp_path / "arq.dxf"
    viewer_path = tmp_path / "arq.viewer.json"
    centers = _write_dxf(dxf_path)
    _write_viewer(viewer_path, centers)
    output_dir = tmp_path / "out"

    rc = main([
        "--source",
        f"{dxf_path}|{viewer_path}|ARQUITECTURA|ARQ.dwg|arq",
        "--output-dir",
        str(output_dir),
        "--no-aps-fallback",
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert (output_dir / "plan_geometry.hybrid.json").is_file()
    assert (output_dir / "hybrid_geometry_audit.json").is_file()
    assert (output_dir / "hybrid_geometry_audit.md").is_file()
    assert "plan_geometry.hybrid.json" in captured.out


def test_discover_hybrid_sources_matches_dxf_to_viewer_urn(tmp_path: Path) -> None:
    inputs_dir = tmp_path / "inputs"
    cache_dir = tmp_path / "cache"
    inputs_dir.mkdir()
    cache_dir.mkdir()
    dxf_path = inputs_dir / "PLANOS ARQ.dxf"
    dxf_path.write_text("0\nEOF\n", encoding="utf-8")
    urn = base64.b64encode(b"urn:adsk.objects:os.object:bucket/PLANOS ARQ.dwg").decode("ascii").rstrip("=")
    viewer_path = cache_dir / f"{urn}.viewer.json"
    viewer_path.write_text(json.dumps({"urn": urn, "views": []}), encoding="utf-8")

    sources = discover_hybrid_sources(
        inputs_dir=inputs_dir,
        cache_dir=cache_dir,
        discipline_for_path=lambda _path: "ARQUITECTURA",
    )

    assert len(sources) == 1
    assert sources[0].dxf_path == dxf_path
    assert sources[0].viewer_json_path == viewer_path
    assert sources[0].discipline == "ARQUITECTURA"
    assert sources[0].file_name == "PLANOS ARQ.dxf"
