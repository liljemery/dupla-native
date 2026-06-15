#!/usr/bin/env python3
"""
Demo: motor 2.5D + registro de niveles usando datos de ejemplo alineados a NASAS 09.

Uso:
  python scripts/demo_coordination_nasas.py
  python scripts/demo_coordination_nasas.py --registry aps_integration/NASAS\\ 09/coordination/sample_project_levels.json

No requiere corrida de visión: construye dos elementos ficticios (viga vs conducto)
que comparten huella en planta y se solapan en Z.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coordination import (
    Discipline,
    Element25D,
    ZInterval,
    clash_pairs,
    conflicts_to_conflict_notes,
)
from coordination.core.registry import ProjectLevelRegistryDocument

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dupla.demo.coordination")


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo coordinación 2.5D (NASAS 09)")
    parser.add_argument(
        "--registry",
        type=Path,
        default=REPO_ROOT / "aps_integration" / "NASAS 09" / "coordination" / "sample_project_levels.json",
        help="JSON con ProjectLevelRegistryDocument",
    )
    args = parser.parse_args()

    if not args.registry.is_file():
        logger.error("No se encontró registro: %s", args.registry)
        raise SystemExit(1)

    doc = ProjectLevelRegistryDocument.model_validate(
        json.loads(args.registry.read_text(encoding="utf-8"))
    )
    registry = doc.to_registry()
    for cand in ("NPT_P1", "NASAS_ARQ_P1_NPT", "NASAS_Z_0"):
        if cand in registry.root:
            level_id = cand
            break
    else:
        level_id = next(iter(registry.root.keys()))

    # Misma losa en planta (mm): conflicto clásico MEP vs estructura
    footprint = [(0.0, 0.0), (3000.0, 0.0), (3000.0, 800.0), (0.0, 800.0)]

    duct = Element25D(
        id="nasas_demo_duct",
        source_ref="demo:duct",
        discipline=Discipline.MEP_HVAC,
        category="duct",
        footprint_coords_mm=footprint,
        z_data=ZInterval(
            level_id=level_id,
            z_ref_raw_mm=2700.0,
            thickness_mm=300.0,
            reference_point="bottom",
            invert_level_hint=False,
            clearance_required_mm=0.0,
            measurement_uncertainty_mm=25.0,
        ),
        metadata={"note": "Conducto bajo forjado — cotas ilustrativas"},
    )

    beam = Element25D(
        id="nasas_demo_beam",
        source_ref="demo:beam",
        discipline=Discipline.STRUC,
        category="beam",
        footprint_coords_mm=footprint,
        z_data=ZInterval(
            level_id=level_id,
            z_ref_raw_mm=2750.0,
            thickness_mm=600.0,
            reference_point="bottom",
            clearance_required_mm=0.0,
            measurement_uncertainty_mm=15.0,
        ),
        metadata={"note": "Viga — demo"},
    )

    conflicts = clash_pairs([duct, beam], registry, strict_levels=True)
    print(f"Proyecto (registro): {doc.project_name!r}")
    print(f"Niveles cargados: {list(registry.root.keys())}")
    print(f"Conflictos detectados: {len(conflicts)}")
    for line in conflicts_to_conflict_notes(conflicts):
        print(" ", line)


if __name__ == "__main__":
    main()
