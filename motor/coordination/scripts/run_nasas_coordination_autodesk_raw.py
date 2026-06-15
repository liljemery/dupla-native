#!/usr/bin/env python3
"""
Clash 2.5D prototipo usando **datos reales** del merge NASAS (export APS `autodesk_raw.json`).

Limitación honesta: el JSON de propiedades no incluye vértices en planta; las huellas son
cuadrados equivalentes por área, centrados en el origen, para poder ejecutar Shapely.
Las cotas Z usan elevación APS si es distinta de cero; si no, valores heurísticos típicos
(viga vs servicios en forjado) — revisar en obra.

Uso:
  python scripts/run_nasas_coordination_autodesk_raw.py
  python scripts/run_nasas_coordination_autodesk_raw.py --raw path/to/*.autodesk_raw.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coordination import clash_pairs, conflicts_to_conflict_notes
from coordination.extraction.from_autodesk_properties import (
    load_autodesk_raw,
    pick_best_entities,
    picks_to_elements,
)
from coordination.core.registry import ProjectLevelRegistryDocument

DEFAULT_RAW = (
    REPO_ROOT
    / "aps_integration"
    / "NASAS 09"
    / "outputs"
    / "corridas"
    / "_cad_merge"
    / "27.11.2025 LAS NASAS 09, DUPLA.autodesk_raw.json"
)
DEFAULT_REGISTRY = (
    REPO_ROOT
    / "aps_integration"
    / "NASAS 09"
    / "coordination"
    / "sample_project_levels.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Clash NASAS desde autodesk_raw.json")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--min-area-m2", type=float, default=1.0)
    args = parser.parse_args()

    if not args.raw.is_file():
        print("No existe autodesk_raw:", args.raw, file=sys.stderr)
        return 1
    if not args.registry.is_file():
        print("No existe registro de niveles:", args.registry, file=sys.stderr)
        return 1

    raw = load_autodesk_raw(args.raw)
    struct, mep = pick_best_entities(raw, min_area_m2=args.min_area_m2)
    print("=== Entidades elegidas (mayor área por disciplina) ===")
    print("Estructura:", struct)
    print("MEP (EL*/inst.):", mep)
    if struct is None or mep is None:
        print(
            "\nNo hay par estructura+MEP con área suficiente. "
            "Baja --min-area-m2 o revisa capas en el DWG merge.",
            file=sys.stderr,
        )
        return 2

    doc = ProjectLevelRegistryDocument.model_validate(
        json.loads(args.registry.read_text(encoding="utf-8"))
    )
    registry = doc.to_registry()
    level_id = "NPT_P1" if "NPT_P1" in registry.root else "NASAS_ARQ_P1_NPT"

    elements = picks_to_elements(struct, mep, level_id=level_id)
    conflicts = clash_pairs(elements, registry, strict_levels=True)
    print("\n=== Registro ===", doc.project_name)
    print("Nivel usado:", level_id)
    print("\n=== Conflictos ===", len(conflicts))
    for line in conflicts_to_conflict_notes(conflicts):
        print(" ", line)
    for el in elements:
        print("\n", el.id, el.metadata)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
