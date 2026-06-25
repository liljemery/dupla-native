#!/usr/bin/env python3
"""Smoke-test DWG→DXF→geometry for local CAD pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_MOTOR = Path(__file__).resolve().parents[1] / "motor"
if _MOTOR.is_dir() and str(_MOTOR) not in sys.path:
    sys.path.insert(0, str(_MOTOR))

from coordination.extraction.libredwg_convert import (
    DwgConvertError,
    classify_dwg2dxf_error,
    convert_dwg_to_dxf,
    is_binary_dwg,
    libredwg_version,
)
from coordination.extraction.local_cad_pipeline import extract_cad_facts


def _layer_count(payload: dict) -> int:
    cad = payload.get("cad_facts") if isinstance(payload, dict) else None
    if not isinstance(cad, dict):
        return 0
    inner = cad.get("cad_facts")
    if isinstance(inner, dict):
        layers = inner.get("layers")
        if isinstance(layers, dict):
            return len(layers)
    layers = cad.get("layers")
    return len(layers) if isinstance(layers, dict) else 0


def _run(path: Path) -> int:
    print(f"libredwg={libredwg_version()}")
    if not path.is_file():
        print(f"MISSING {path}")
        return 1
    if path.suffix.lower() == ".dwg" and is_binary_dwg(path):
        try:
            dxf_path = convert_dwg_to_dxf(path, output_dir=path.parent / ".dxf_cache")
            print(f"  dwg2dxf OK -> {dxf_path.name}")
        except DwgConvertError as exc:
            print(f"  dwg2dxf FAIL {exc.error_code}: {exc.detail[:200]}")
            return 1
        except Exception as exc:
            code = classify_dwg2dxf_error(str(exc), returncode=1)
            print(f"  dwg2dxf FAIL {code}: {exc}")
            return 1
    try:
        payload = extract_cad_facts(path)
        layers = _layer_count(payload)
        records = payload.get("total_objects") if isinstance(payload, dict) else 0
        print(f"  extract OK layers={layers} records={records}")
        return 0 if layers > 0 else 2
    except Exception as exc:
        print(f"  extract FAIL: {exc}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="DWG convert + extract smoke test")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    worst = 0
    for path in args.paths:
        print(path.name)
        worst = max(worst, _run(path))
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
