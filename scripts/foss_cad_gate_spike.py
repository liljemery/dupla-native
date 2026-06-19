#!/usr/bin/env python3
"""Fase 0: validate LibreDWG dwg2dxf + ezdxf on real or sample DWGs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MOTOR = REPO / "motor"
if str(MOTOR) not in sys.path:
    sys.path.insert(0, str(MOTOR))

from coordination.extraction.dxf_geometry import extract_dxf_geometry
from coordination.extraction.libredwg_convert import convert_dwg_to_dxf, dwg2dxf_available, is_binary_dwg
from coordination.extraction.local_cad_pipeline import extract_cad_facts


def _audit_dxf(dxf_path: Path) -> dict[str, object]:
    extraction = extract_dxf_geometry(dxf_path, "ARQUITECTURA")
    physical = [record for record in extraction.records if record.is_physical]
    with_bounds = [
        record
        for record in physical
        if abs(record.model_bounds[2] - record.model_bounds[0]) > 0
        or abs(record.model_bounds[3] - record.model_bounds[1]) > 0
    ]
    ratio = len(with_bounds) / len(physical) if physical else 0.0
    return {
        "dxf_path": str(dxf_path),
        "entity_count": len(extraction.records),
        "physical_count": len(physical),
        "bounded_physical_ratio": round(ratio, 3),
        "insunits": extraction.insunits,
        "go": ratio >= 0.8 and len(physical) > 0,
    }


def _process_path(path: Path, work_dir: Path) -> dict[str, object]:
    path = path.resolve()
    result: dict[str, object] = {"source": str(path), "suffix": path.suffix.lower()}
    if path.suffix.lower() == ".dxf":
        result.update(_audit_dxf(path))
        return result
    if path.suffix.lower() != ".dwg":
        result["go"] = False
        result["error"] = "unsupported_suffix"
        return result
    if not is_binary_dwg(path):
        result["go"] = False
        result["error"] = "not_binary_dwg"
        return result
    if not dwg2dxf_available():
        result["go"] = False
        result["error"] = "dwg2dxf_missing"
        return result
    try:
        dxf_path = convert_dwg_to_dxf(path, output_dir=work_dir / path.stem)
        result["converted_dxf"] = str(dxf_path)
        result.update(_audit_dxf(dxf_path))
        facts = extract_cad_facts(path, work_dir=work_dir / path.stem)
        result["cad_facts_layers"] = len(facts.get("cad_facts", {}).get("layers", {}))
    except Exception as exc:
        result["go"] = False
        result["error"] = str(exc)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="FOSS CAD gate spike (LibreDWG + ezdxf)")
    parser.add_argument("paths", nargs="+", type=Path, help="DWG/DXF files or directories")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    inputs: list[Path] = []
    for raw in args.paths:
        if raw.is_dir():
            inputs.extend(sorted(raw.rglob("*.dwg")))
            inputs.extend(sorted(raw.rglob("*.dxf")))
        elif raw.is_file():
            inputs.append(raw)

    work_dir = Path("/tmp/foss_cad_gate")
    work_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "dwg2dxf_available": dwg2dxf_available(),
        "files": [_process_path(path, work_dir) for path in inputs],
    }
    report["go_count"] = sum(1 for item in report["files"] if item.get("go"))
    report["no_go_count"] = len(report["files"]) - report["go_count"]

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["go_count"] == len(report["files"]) or not report["files"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
