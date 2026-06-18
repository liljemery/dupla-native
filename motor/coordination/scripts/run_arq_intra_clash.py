#!/usr/bin/env python3
"""End-to-end intra-discipline clash test on ARQ (SERENA 18).

ARQ is the reference/identity frame (Phase-1 clean), so this needs no common
frame: it detects conflicting-layer overlaps inside ARQ, self-renders the
cleaned plan with real bbox overlays, and emits a GA-FO-08 PDF.

Run (conda python):
    PYTHONPATH=motor /Users/samuelfernandez/anaconda3/bin/python \
        motor/coordination/scripts/run_arq_intra_clash.py

Optional: a JSON config override file as argv[1] to replace the layer pairs.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

from coordination.core.intra_clash import (
    ClashConfig,
    IntraIncident,
    LayerPairRule,
    detect,
    group_incidents,
    prepare_elements,
)
from coordination.reporting.plan_render import render_incident, render_overview

RUN_DIR = Path("var/coord_outputs/serena18_run")
GEOMETRY_PATH = RUN_DIR / "sanitized_geometry" / "ARQ.sanitized.geometry.json"
OUT_DIR = RUN_DIR / "arq_intra_clash"
PROJECT_NAME = "SERENA 18"
MAX_DETAIL_TILES = 12  # matplotlib debug tiles only; PDF annex has no cap

# ── GA-FO-08 "LISTA DE CHEQUEO - PLANOS" institutional form metadata ────────
PROCESO_LINE = "GESTIÓN DE ARQUITECTURA Y CONTROL DE PLANOS"
FORM_CODE = "GA-FO-08 (04.2025) V.01"
LDC_NUMBER = "LDC-SERENA18-01"
REVISOR = "Revisión Técnica Dupla"
DISCIPLINE_LABEL = "ARQUITECTURA"
SHEET_CODE = "ARQ-ID"
CORRELACION = "Intra-disciplina (ARQ)"
SEVERITY_ES = {"critical": "CRÍTICA", "major": "MAYOR", "minor": "MENOR"}


# ── EDITABLE CLASH CRITERION ────────────────────────────────────────────────
# Conflicting layer pairs for this interior-design (ID) ARQ plan. Each rule:
#   (layer_a, layer_b, human label, min_overlap_frac of the smaller bbox, weight)
# This plan has no A-WALL / Columnas structural layers (only I-* interior
# layers + a single I-COLUMN), so the default pairs target interior conflicts.
DEFAULT_PAIRS = [
    # Cross-system interferences (genuinely actionable -> escalated)
    LayerPairRule(
        "I-PLUMB-FIXT", "I-FURN", "Aparato sanitario bajo mobiliario (acceso bloqueado)", 0.40, 1.5
    ),
    LayerPairRule("I-EQUIPMENT", "I-FURN", "Equipo solapado con mobiliario", 0.40, 1.3),
    LayerPairRule("I-EQUIPMENT", "I-MILLWORK", "Equipo solapado con carpinteria", 0.40, 1.2),
    LayerPairRule("I-COLUMN", "I-FURN", "Mobiliario sobre columna", 0.30, 1.5),
    LayerPairRule("I-COLUMN", "I-MILLWORK", "Carpinteria sobre columna", 0.30, 1.5),
    # Duplicate-geometry on the same layer (drafting error -> review)
    LayerPairRule("I-WALL", "I-WALL", "Muro duplicado / solapado", 0.70, 1.2),
    LayerPairRule("I-MILLWORK", "I-MILLWORK", "Carpinteria duplicada", 0.70, 1.2),
    LayerPairRule(
        "I-MILLWORK-FULL-HEIGHT",
        "I-MILLWORK-FULL-HEIGHT",
        "Carpinteria full-height duplicada",
        0.70,
        1.2,
    ),
    LayerPairRule(
        "I-MILLWORK", "I-MILLWORK-FULL-HEIGHT", "Carpinteria solapada (full-height vs normal)", 0.60, 1.1
    ),
    # Furniture-on-furniture: on an interior plan this is mostly expected
    # co-location (chairs under tables, sets). Only near-total duplicates are
    # flagged, demoted to minor (weight < 1) so it never dominates the report.
    LayerPairRule("I-FURN", "I-FURN", "Mobiliario solapado (posible duplicado)", 0.85, 0.5),
]

# Layers excluded from conflict logic (annotation, different Z-plane finishes,
# and "hidden" construction lines that legitimately underlie real objects).
EXCLUDE_LAYERS = {
    "I-FURN-HIDDEN",
    "I-MILLWORK-HIDDEN",
    "I-FLOR-FIN",
    "I-FLOOR-FIN",
    "I-FLOR-STRS-SYMB",
    "A-FLOR-STRS-SYMB",
    "I-CLNG",
    "I-CEILING-MEDIA",
    "I-DRAPERY",
    "I-FURN-RUGS",
    "I-WALL-HATCH-EXISTING",
}


def load_config(argv: list[str]) -> ClashConfig:
    if len(argv) > 1 and Path(argv[1]).is_file():
        raw = json.loads(Path(argv[1]).read_text())
        pairs = [
            LayerPairRule(
                p["layer_a"],
                p["layer_b"],
                p.get("label", f"{p['layer_a']} x {p['layer_b']}"),
                float(p.get("min_overlap_frac", 0.5)),
                float(p.get("weight", 1.0)),
            )
            for p in raw.get("pairs", [])
        ]
        return ClashConfig(
            pairs=pairs,
            exclude_layers=set(raw.get("exclude_layers", [])),
            min_abs_area_m2=float(raw.get("min_abs_area_m2", 0.02)),
            incident_cell_m=float(raw.get("incident_cell_m", 3.0)),
            max_element_area_m2=float(raw.get("max_element_area_m2", 20.0)),
        )
    return ClashConfig(pairs=DEFAULT_PAIRS, exclude_layers=EXCLUDE_LAYERS)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tiles_dir = OUT_DIR / "tiles"
    tiles_dir.mkdir(exist_ok=True)

    print("=" * 70)
    print("  ARQ INTRA-DISCIPLINE CLASH — SERENA 18 (identity/reference frame)")
    print("=" * 70)

    # ── Checkpoint 1: load + element counts ────────────────────────────────
    geometry = json.loads(GEOMETRY_PATH.read_text())
    config = load_config(sys.argv)
    elements, prep_meta = prepare_elements(
        geometry, quality_allow=config.quality_allow, max_element_area_m2=config.max_element_area_m2
    )

    print("\n[1] LOAD ARQ NORMALIZED GEOMETRY")
    print(f"    source        : {GEOMETRY_PATH}")
    print(f"    factor->meters: {geometry['unit_sanitation']['factor_to_meters']}")
    print(f"    cleaned size  : {geometry['cleanup']['cleaned_outline_size_m']} m")
    print(f"    oversize guard: bbox area > {config.max_element_area_m2} m^2 dropped as unlocalizable container")
    print(
        f"    elements kept : {prep_meta['kept']} physical good+coarse in main cluster "
        f"(skipped {prep_meta['skipped']})"
    )
    layer_hist = collections.Counter(el.layer for el in elements)
    print("    top layers (physical good+coarse, main cluster):")
    for lyr, n in layer_hist.most_common(18):
        mark = "  <- in criterion" if lyr in config.relevant_layers() and lyr not in config.exclude_layers else ""
        print(f"        {n:5d}  {lyr}{mark}")

    print("\n    CLASH CRITERION (editable conflicting layer pairs):")
    for rule in config.pairs:
        print(
            f"        {rule.layer_a:>24}  x  {rule.layer_b:<24}  "
            f"min_overlap>={rule.min_overlap_frac:.0%}  w={rule.weight}  [{rule.label}]"
        )
    print(f"        excluded layers: {sorted(config.exclude_layers)}")

    # ── Checkpoint 2: detect + group ───────────────────────────────────────
    clashes = detect(elements, config)
    incidents = group_incidents(clashes, cell_m=config.incident_cell_m)
    sev_counts = collections.Counter(inc.severity for inc in incidents)
    print("\n[2] DETECT INTRA-ARQ CLASHES")
    print(f"    raw overlaps  : {len(clashes)}")
    print(f"    incidents     : {len(incidents)}  (severity {dict(sev_counts)})")
    pair_hist = collections.Counter(c.rule_label for c in clashes)
    for label, n in pair_hist.most_common():
        print(f"        {n:5d}  {label}")
    print("    top incidents:")
    for inc in incidents[:8]:
        rep = inc.representative
        print(
            f"        {inc.incident_id} [{inc.severity}] {rep.layer_a} x {rep.layer_b} "
            f"@({inc.centroid_m[0]:.1f},{inc.centroid_m[1]:.1f}) "
            f"overlap={rep.overlap_area_m2:.2f} m^2 ({rep.overlap_frac:.0%}) "
            f"handles {rep.handle_a}/{rep.handle_b}  members={len(inc.members)}"
        )

    # persist machine-readable results
    results = {
        "project": PROJECT_NAME,
        "discipline": "ARQ",
        "frame": "identity (reference)",
        "render_source": (
            "APS (SVF 2D sheet) + self-render"
            if (OUT_DIR / "aps_plan_annotated.png").is_file()
            else "self (ezdxf-derived bbox plan)"
        ),
        "geometry_source": str(GEOMETRY_PATH),
        "elements_analyzed": prep_meta["kept"],
        "elements_skipped": prep_meta["skipped"],
        "max_element_area_m2": config.max_element_area_m2,
        "criterion": [
            {
                "layer_a": r.layer_a,
                "layer_b": r.layer_b,
                "label": r.label,
                "min_overlap_frac": r.min_overlap_frac,
                "weight": r.weight,
            }
            for r in config.pairs
        ],
        "excluded_layers": sorted(config.exclude_layers),
        "raw_overlaps": len(clashes),
        "incident_count": len(incidents),
        "severity_counts": dict(sev_counts),
        "incidents": [inc.as_dict() for inc in incidents],
    }
    (OUT_DIR / "clash_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))

    # ── Checkpoint 3: render ───────────────────────────────────────────────
    print("\n[3] RENDER (self-render: ezdxf-derived bbox plan, identity frame)")
    overview_png = render_overview(
        elements,
        incidents,
        OUT_DIR / "overview.png",
        title=f"{PROJECT_NAME} — ARQ intra-discipline clashes (plan general)",
    )
    print(f"    overview : {overview_png}")
    detail_pngs: list[tuple[IntraIncident, str]] = []
    for inc in incidents[:MAX_DETAIL_TILES]:
        png = render_incident(
            inc,
            elements,
            tiles_dir / f"{inc.incident_id}.png",
            title=f"{inc.incident_id} [{inc.severity}] — {inc.representative.rule_label}",
        )
        detail_pngs.append((inc, png))
    print(f"    incident tiles: {len(detail_pngs)} (top {MAX_DETAIL_TILES} of {len(incidents)})")

    # ── Checkpoint 4: GA-FO-08 PDF ─────────────────────────────────────────
    import datetime as _dt

    sheet_title = Path(geometry.get("source_dwg") or "ARQ").stem
    sheet_mtime = ((geometry.get("source_fingerprint") or {}).get("mtime"))
    sheet_date = _dt.datetime.fromtimestamp(sheet_mtime).strftime("%d.%m.%Y") if sheet_mtime else "—"
    # APS literal plan pages (overview clean + detail clusters) when available.
    aps_index = OUT_DIR / "aps_overlay_index.json"
    aps_annex: list[tuple[str, str]] = []
    label_map: dict[str, tuple[str, str]] = {}
    overlay_idx: dict | None = None
    if aps_index.is_file():
        overlay_idx = json.loads(aps_index.read_text())
        annex_letter = ord("A")
        if overlay_idx.get("overview"):
            aps_annex.append((f"{SHEET_CODE} — lámina APS (plano completo)", overlay_idx["overview"]))
            annex_letter += 1
        for dp in overlay_idx.get("detail_pages") or []:
            lbl = f"1-{chr(annex_letter)}"
            n = dp["n"]
            pairs = dp.get("layer_pairs") or []
            if pairs:
                pair_txt = "; ".join(pairs[:3])
                if len(pairs) > 3:
                    pair_txt += f" (+{len(pairs) - 3} más)"
                title = f"{SHEET_CODE} — detalle: {pair_txt} ({n} clash{'es' if n != 1 else ''})"
            else:
                title = f"{SHEET_CODE} — detalle incidencias ({n} clash{'es' if n != 1 else ''})"
            aps_annex.append((title, dp["path"]))
            for j, iid in enumerate(dp.get("incident_ids") or []):
                label_map[iid] = (lbl, f"C-{dp['label_from'] + j:03d}")
            annex_letter += 1
    render_source = (
        "APS (SVF 2D sheet) literal screenshots + revision-cloud detail pages"
        if aps_annex else "self (ezdxf-derived bbox plan; no APS sheet present)"
    )
    meta = {
        "project": PROJECT_NAME,
        "fecha": _dt.date.today().strftime("%d.%m.%Y"),
        "ldc": LDC_NUMBER,
        "revisor": REVISOR,
        "sheet_code": SHEET_CODE,
        "sheet_title": sheet_title,
        "sheet_date": sheet_date,
        "sheet_rev": "REV. 1",
        "render_source": render_source,
    }
    pdf_path = build_ga_fo_08(
        incidents=incidents,
        overview_png=overview_png,
        detail_pngs=detail_pngs,
        config=config,
        elements_analyzed=prep_meta["kept"],
        sev_counts=sev_counts,
        pair_hist=pair_hist,
        meta=meta,
        aps_annex=aps_annex,
        label_map=label_map,
        overlay_index=overlay_idx,
    )
    print("\n[4] BUILD GA-FO-08 PDF")
    print(f"    pdf : {pdf_path}")

    # ── Checkpoint 5: summary ──────────────────────────────────────────────
    print("\n[5] CHECKPOINT")
    print(f"    PDF path        : {pdf_path}")
    print(f"    incidents       : {len(incidents)} (severity {dict(sev_counts)})")
    print(f"    render source   : {render_source}")
    print(f"    results json    : {OUT_DIR / 'clash_results.json'}")
    print("    spot-check (boxes sit on real elements — identity frame, model coords):")
    for inc in incidents[:3]:
        rep = inc.representative
        print(
            f"        {inc.incident_id}: overlap bbox {tuple(round(v,2) for v in rep.overlap_bounds_m)} m "
            f"between #{rep.handle_a} ({rep.layer_a}) and #{rep.handle_b} ({rep.layer_b})"
        )


_SEV_RANK = {"critical": 0, "major": 1, "minor": 2}


def _observation_lines(
    incidents: list[IntraIncident],
    label_map: dict[str, tuple[str, str]],
) -> list[str]:
    """Fallback: all incidents in one block (when no APS detail index)."""
    lines = ["El plano presenta las siguientes observaciones:"]
    for n, inc in enumerate(incidents, start=1):
        rep = inc.representative
        c_lbl = label_map.get(inc.incident_id, ("", f"C-{n:03d}"))[1]
        sev = SEVERITY_ES.get(inc.severity, inc.severity.upper())
        lines.append(
            f"- {c_lbl}: {rep.layer_a} vs {rep.layer_b} — {rep.rule_label} "
            f"({rep.overlap_area_m2:.2f} m², {sev})."
        )
    return lines


def _entries_from_clusters(
    incidents: list[IntraIncident],
    label_map: dict[str, tuple[str, str]],
    meta: dict,
    idx: dict | None,
) -> list:
    """One table row per spatial cluster (matches reference: row per plan sheet)."""
    from coordination.reporting import ga_fo_08 as form

    if not idx or not idx.get("detail_pages"):
        return [form.Entry(
            discipline=DISCIPLINE_LABEL,
            numero_plano=meta["sheet_code"],
            titulo=meta["sheet_title"],
            descripcion="Revisión de coordinación intradisciplinar (ARQ).",
            fecha=meta["sheet_date"],
            revision=meta["sheet_rev"],
            correlacion=[],
            observation_lines=_observation_lines(incidents, label_map),
            annex_labels=[],
        )]

    by_id = {inc.incident_id: inc for inc in incidents}
    entries: list = []
    annex_labels_all: list[str] = ["1-A"]  # overview

    # First row: plan summary + reference to full-sheet annex.
    entries.append(form.Entry(
        discipline=DISCIPLINE_LABEL,
        numero_plano=meta["sheet_code"],
        titulo=meta["sheet_title"],
        descripcion="Plano base — revisión de coordinación intradisciplinar.",
        fecha=meta["sheet_date"],
        revision=meta["sheet_rev"],
        correlacion=[],
        observation_lines=[
            f"Plano {meta['sheet_code']} — {meta['sheet_title']}.",
            f"Total: {len(incidents)} incidencias detectadas.",
            "Ver Anexo 1-A (plano completo).",
        ],
        annex_labels=["1-A"],
    ))

    for dp in idx["detail_pages"]:
        annex_lbl = f"1-{chr(ord('A') + len(entries))}"  # 1-B, 1-C, …
        annex_labels_all.append(annex_lbl)
        group_incs = [by_id[iid] for iid in dp.get("incident_ids", []) if iid in by_id]
        pairs = sorted({
            f"{inc.representative.layer_a} vs {inc.representative.layer_b}"
            for inc in group_incs
        })
        lines = [f"Zona de incidencias ({dp['n']} clash{'es' if dp['n'] != 1 else ''}):"]
        if pairs:
            lines.append("Pares de capas: " + "; ".join(pairs) + ".")
        for inc in group_incs:
            rep = inc.representative
            _, c_lbl = label_map.get(inc.incident_id, ("", ""))
            sev = SEVERITY_ES.get(inc.severity, inc.severity.upper())
            lines.append(
                f"- {c_lbl}: {rep.layer_a} vs {rep.layer_b} — {rep.rule_label} "
                f"({rep.overlap_area_m2:.2f} m², {sev})."
            )
        lines.append(f"Ver Anexo {annex_lbl} (detalle en plano).")
        entries.append(form.Entry(
            discipline=DISCIPLINE_LABEL,
            numero_plano=meta["sheet_code"],
            titulo=meta["sheet_title"],
            descripcion=f"Detalle zona {dp['group']}.",
            fecha=meta["sheet_date"],
            revision=meta["sheet_rev"],
            correlacion=pairs,
            observation_lines=lines,
            annex_labels=[annex_lbl],
        ))
    return entries


def _discover_discipline_runs(run_dir: Path) -> list[Path]:
    """Find clash output dirs for each discipline iteration under the project run."""
    found = sorted(run_dir.glob("*_intra_clash"))
    if not found and (run_dir / "arq_intra_clash").is_dir():
        found = [run_dir / "arq_intra_clash"]
    return found


def build_ga_fo_08(
    *,
    incidents: list[IntraIncident],
    overview_png: str,
    detail_pngs: list[tuple[IntraIncident, str]],
    config: ClashConfig,
    elements_analyzed: int,
    sev_counts: collections.Counter,
    pair_hist: collections.Counter,
    meta: dict,
    aps_annex: list[tuple[str, str]] | None = None,
    label_map: dict[str, tuple[str, str]] | None = None,
    overlay_index: dict | None = None,
    extra_entries: list | None = None,
    extra_annex: list[tuple[str, str]] | None = None,
) -> str:
    """GA-FO-08 — formato Dupla: una fila por lámina, anexos literales por clúster."""
    from coordination.reporting import ga_fo_08 as form

    label_map = label_map or {}
    aps_annex = aps_annex or []

    entries = _entries_from_clusters(incidents, label_map, meta, overlay_index)
    entries.extend(extra_entries or [])
    annex: list[tuple[str, str]] = list(aps_annex)
    if not annex and overview_png:
        annex.append((f"{meta['sheet_code']} — vista de incidencias", overview_png))
    annex.extend(extra_annex or [])

    logo_left = str(Path(__file__).resolve().parents[1] / "reporting" / "assets" / "grupo-dupla-logo.png")
    out_path = str(OUT_DIR / "GA-FO-08_ARQ_intra_clash.pdf")
    return form.build_checklist_pdf(
        entries=entries,
        project_name=meta["project"],
        out_path=out_path,
        checklist_number=meta["ldc"],
        reviewer_name=meta["revisor"],
        export_date=meta["fecha"],
        logo_left_path=logo_left if Path(logo_left).is_file() else None,
        annex_pages=annex,
    )


if __name__ == "__main__":
    main()
