"""
(P1.5) Los CUADROS como AUTORIDAD.

El cuadro de columnas/vigas/zapatas dice el despiece exacto (acero principal +
estribos + cantidad + longitud). En vez de estimar el acero con un ratio
volumetrico (kg/m3), aqui lo calculamos del despiece con ``rebar.py`` (catalogo
de varillas, perimetro de estribo, recubrimiento) y REEMPLAZAMOS los takeoffs de
``*_reinforcement_kg`` basados en ratio. Cada takeoff resultante queda trazado con
``quantity_source = "cuadro"``.

Tambien expone autoridad de CONTEO para puertas/ventanas: rellena conteos que la
vision no detecto (additivo, nunca reduce) tomando el cuadro como verdad.

Todo es defensivo: si falta el dato, se omite esa fila sin romper el pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("dupla.schedule_authority")

# Cuadro element word -> takeoff element_type prefix.
_ELEMENT_MAP = {
    "columna": "column",
    "column": "column",
    "viga": "beam",
    "beam": "beam",
    "zapata": "footing",
    "footing": "footing",
}

_REINFORCEMENT_TYPES = {
    "column_reinforcement_kg",
    "beam_reinforcement_kg",
    "footing_reinforcement_kg",
}


def _parse_section(spec: Any) -> tuple[float, float] | None:
    try:
        a, b = str(spec).lower().replace("m", "").split("x")
        return float(a), float(b)
    except (ValueError, AttributeError):
        return None


def _steel_kg_for_row(row: dict[str, Any], *, cover_m: float) -> dict[str, Any] | None:
    """Compute total steel kg for one schedule row from its despiece."""
    from disciplines.estructura import rebar

    count = int(row.get("count") or 1)
    length_m = row.get("length_m")
    try:
        length_m = float(length_m) if length_m is not None else None
    except (TypeError, ValueError):
        length_m = None

    main_notation = row.get("main_bars")
    stirrup_notation = row.get("stirrups")

    main_kg = 0.0
    stirrup_kg = 0.0
    breakdown: dict[str, Any] = {}

    if main_notation and length_m:
        bars = rebar.parse_main_bars(str(main_notation))
        if bars:
            mb = rebar.calculate_main_bar_weight(bars, length_m)
            main_kg = mb["total_kg"]
            breakdown["main_bars"] = mb["breakdown"]

    if stirrup_notation and length_m:
        sec = _parse_section(row.get("section"))
        if sec:
            stirrup = rebar.parse_stirrups(str(stirrup_notation))
            if stirrup:
                sw = rebar.calculate_stirrup_weight(
                    stirrup, length_m, sec[0], sec[1], cover_m=cover_m
                )
                stirrup_kg = sw["total_kg"]
                breakdown["stirrups"] = {k: sw[k] for k in ("count", "perimeter_m", "total_length_m")}

    per_element = main_kg + stirrup_kg
    if per_element <= 0:
        return None
    total_kg = round(per_element * count, 2)
    return {
        "mark": row.get("mark"),
        "count": count,
        "length_m": length_m,
        "per_element_kg": round(per_element, 2),
        "total_kg": total_kg,
        "breakdown": breakdown,
    }


def apply_structural_steel_authority(
    takeoffs: list[Any],
    structural_schedule: dict[str, Any] | None,
    *,
    cover_m: float = 0.04,
) -> list[Any]:
    """Replace ratio-based ``*_reinforcement_kg`` with despiece totals from the cuadro.

    Returns a new takeoff list. No-op when the schedule is empty.
    """
    rows = (structural_schedule or {}).get("filas") or []
    if not rows:
        return takeoffs

    # Aggregate despiece steel per mapped element_type.
    kg_by_type: dict[str, float] = {}
    detail_by_type: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        elem = str(row.get("element") or "").lower()
        etype = _ELEMENT_MAP.get(elem)
        if not etype:
            continue
        computed = None
        try:
            computed = _steel_kg_for_row(row, cover_m=cover_m)
        except Exception:
            logger.warning("steel authority: failed on row %r", row.get("mark"), exc_info=True)
        if not computed:
            continue
        kg_by_type[etype] = kg_by_type.get(etype, 0.0) + computed["total_kg"]
        detail_by_type.setdefault(etype, []).append(computed)

    if not kg_by_type:
        logger.info("steel authority: no priceable despiece rows; keeping ratio estimates")
        return takeoffs

    from core.schemas import QuantityTakeoff, QuantityTrace

    # Drop ratio-based reinforcement takeoffs for the element types we now own.
    owned_item_types = {f"{etype}_reinforcement_kg" for etype in kg_by_type}
    kept = [t for t in takeoffs if t.item_type not in owned_item_types]
    dropped = len(takeoffs) - len(kept)

    level_id = takeoffs[0].level_id if takeoffs else None
    new_takeoffs: list[Any] = []
    for etype, total_kg in kg_by_type.items():
        item_type = f"{etype}_reinforcement_kg"
        marks = [d.get("mark") for d in detail_by_type.get(etype, [])]
        new_takeoffs.append(
            QuantityTakeoff(
                item_key=f"cuadro:{etype}:reinforcement_kg",
                item_type=item_type,
                level_id=level_id,
                unit="kg",
                quantity=round(total_kg, 2),
                formula="suma despiece cuadro (main_bars + stirrups) x count",
                inputs={
                    "quantity_source": "cuadro",
                    "element_type": etype,
                    "marks": marks,
                    "despiece": detail_by_type.get(etype, []),
                    "cover_m": cover_m,
                },
                assumptions=[
                    f"Acero de {etype} calculado del despiece del cuadro "
                    f"({len(marks)} marcas), no por ratio volumetrico."
                ],
                trace=QuantityTrace(
                    steps=["Despiece del cuadro estructural -> peso por catalogo de varillas."],
                    metadata={"quantity_source": "cuadro", "marks": marks},
                ),
                confidence=0.95,
                requiere_revision=False,
            )
        )

    logger.info(
        "steel authority: replaced %d ratio takeoffs with %d cuadro-derived (%.0f kg total)",
        dropped, len(new_takeoffs), sum(kg_by_type.values()),
    )
    return kept + new_takeoffs


def apply_opening_count_authority(
    takeoffs: list[Any],
    openings_schedule: dict[str, Any] | None,
) -> list[Any]:
    """Fill door/window counts the vision missed, using the cuadro as truth.

    Additive only: if the inventory already has >= the cuadro count for a type,
    nothing changes. Otherwise the gap is added as a cuadro-sourced takeoff.
    """
    rows = (openings_schedule or {}).get("filas") or []
    if not rows:
        return takeoffs

    # Sum cuadro counts per kind (door/window).
    cuadro_doors = 0
    cuadro_windows = 0
    for row in rows:
        kind = str(row.get("kind") or "").lower()
        cnt = int(row.get("count") or 0)
        if "puerta" in kind or kind == "door":
            cuadro_doors += cnt
        elif "ventana" in kind or kind == "window":
            cuadro_windows += cnt

    have_doors = sum(int(t.quantity or 0) for t in takeoffs if t.item_type == "door_count")
    have_windows = sum(int(t.quantity or 0) for t in takeoffs if t.item_type == "window_count")

    from core.schemas import QuantityTakeoff, QuantityTrace

    additions: list[Any] = []
    level_id = takeoffs[0].level_id if takeoffs else None
    for item_type, cuadro_cnt, have in (
        ("door_count", cuadro_doors, have_doors),
        ("window_count", cuadro_windows, have_windows),
    ):
        gap = cuadro_cnt - have
        if gap > 0:
            additions.append(
                QuantityTakeoff(
                    item_key=f"cuadro:{item_type}:gap",
                    item_type=item_type,
                    level_id=level_id,
                    unit="ud",
                    quantity=float(gap),
                    formula=f"cuadro({cuadro_cnt}) - detectado({have})",
                    inputs={"quantity_source": "cuadro", "cuadro_count": cuadro_cnt, "detected": have},
                    assumptions=[
                        f"Conteo completado desde el cuadro: faltaban {gap} respecto al cuadro."
                    ],
                    trace=QuantityTrace(metadata={"quantity_source": "cuadro"}),
                    confidence=0.8,
                    requiere_revision=True,
                )
            )

    if additions:
        logger.info("opening authority: +%d gap takeoffs from cuadro", len(additions))
    return list(takeoffs) + additions
