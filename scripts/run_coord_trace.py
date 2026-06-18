#!/usr/bin/env python3
"""Run one end-to-end COORD instrumentation trace for a single clash incident."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MOTOR = REPO / "motor"
BACKEND = REPO / "backend"
for p in (str(MOTOR), str(BACKEND)):
    if p not in sys.path:
        sys.path.insert(0, p)

DEFAULT_JOB = Path(
    "/Users/samuelfernandez/dupla-native/var/coord_outputs/"
    "09a33a3e-9230-4aa2-a445-30df0bc2aee5"
)
TARGET_INCIDENT = "incident_0001"
ARQ_FILE = "PLANOS ARQ.-LAS NASAS 09-20260320.dwg"


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )
    logging.getLogger("COORD").setLevel(logging.INFO)


def _get_aps_token() -> str:
    import requests

    client_id = os.getenv("CLIENT_ID", "")
    client_secret = os.getenv("CLIENT_SECRET", "")
    if not client_id or not client_secret:
        env_path = BACKEND / ".env"
        if env_path.is_file():
            for line in env_path.read_text().splitlines():
                if line.startswith("CLIENT_ID="):
                    client_id = line.split("=", 1)[1].strip()
                elif line.startswith("CLIENT_SECRET="):
                    client_secret = line.split("=", 1)[1].strip()
    r = requests.post(
        "https://developer.api.autodesk.com/authentication/v2/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": "data:read viewables:read",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _load_incident(job_dir: Path) -> dict:
    data = json.loads((job_dir / "primary_incidents.json").read_text(encoding="utf-8"))
    for inc in data.get("incidents", []):
        if inc.get("incident_id") == TARGET_INCIDENT:
            return inc
    raise SystemExit(f"{TARGET_INCIDENT} not found in {job_dir / 'primary_incidents.json'}")


def _run_extraction(job_dir: Path, incident: dict) -> None:
    from coordination.core.models_25d import Discipline
    from coordination.extraction.from_dwg_accore import extract_elements_from_accore_payload

    rep = incident["representative_conflict"]
    bounds = rep["plan_intersection_bounds_mm"]
    x0, y0, x1, y1 = bounds
    payload = {
        "UnitsToMmFactor": 1.0,
        "Entities": [
            {
                "Type": "Polyline",
                "Layer": "COORD_TRACE",
                "Handle": "TRACE01",
                "Bounds": {
                    "Min": {"X": x0, "Y": y0, "Z": 0.0},
                    "Max": {"X": x1, "Y": y1, "Z": 0.0},
                },
                "Vertices": [
                    {"X": x0, "Y": y0},
                    {"X": x1, "Y": y0},
                    {"X": x1, "Y": y1},
                    {"X": x0, "Y": y1},
                ],
            }
        ],
    }
    dwg_path = job_dir / "inputs" / "PLANOS RECIBIDOS" / "ARQUITECTONICOS" / ARQ_FILE
    extract_elements_from_accore_payload(
        payload,
        path=dwg_path,
        discipline=Discipline.ARCH,
        level_id="NASAS_ARQ_P1_NPT",
        translation_mm=(0.0, 0.0),
        min_area_mm2=1.0,
        max_entities=10,
        z_thickness_mm=250.0,
        z_ref_mm=None,
    )


def _run_clash(job_dir: Path, incident: dict) -> None:
    from coordination.core.clash import clash_pairs
    from coordination.core.models_25d import Discipline, Element25D, ZInterval
    from coordination.core.registry import ProjectLevel, ProjectLevelRegistry

    rep = incident["representative_conflict"]
    bounds = rep["plan_intersection_bounds_mm"]
    x0, y0, x1, y1 = bounds
    cx, cy = rep["plan_intersection_centroid_mm"]
    half = max((x1 - x0) / 2, 50.0)

    def _rect(el_id: str, discipline: Discipline, ox: float, oy: float) -> Element25D:
        footprint = [
            (ox - half, oy - half),
            (ox + half, oy - half),
            (ox + half, oy + half),
            (ox - half, oy + half),
        ]
        return Element25D(
            id=el_id,
            source_ref=f"trace|{discipline.value}",
            discipline=discipline,
            category="trace",
            footprint_coords_mm=footprint,
            z_data=ZInterval(level_id="NASAS_ARQ_P1_NPT", z_ref_raw_mm=0.0, thickness_mm=300.0),
            metadata={"geometry_source": "coord_trace"},
        )

    elements = [
        _rect("trace_arq", Discipline.ARCH, cx, cy),
        _rect("trace_elec", Discipline.MEP_ELEC, cx, cy),
    ]
    registry = ProjectLevelRegistry(
        {
            "NASAS_ARQ_P1_NPT": ProjectLevel(
                id="NASAS_ARQ_P1_NPT",
                name="P1",
                offset_to_project_zero_mm=0.0,
            )
        }
    )
    clash_pairs(elements, registry, min_plan_area_mm2=1.0)


def _run_viewer_and_pdf(job_dir: Path, incident: dict, aps_token: str) -> str | None:
    from app.services.clash_reports.aps_viewer_renderer import render_plan_pages
    from app.services.clash_reports.checklist_pdf import _scaled_image_path
    from app.services.clash_reports.clash_plan_images import _build_clash_list

    rep = incident["representative_conflict"]
    clash = {
        "bounds_mm": rep["plan_intersection_bounds_mm"],
        "centroid_mm": rep["plan_intersection_centroid_mm"],
        "clash_type": rep.get("clash_type", "HARD"),
    }
    clashes = _build_clash_list([incident])

    from app.services.clash_reports.clash_plan_images import get_urn_from_cache

    record = get_urn_from_cache(str(job_dir / "cache"), ARQ_FILE)
    if not record:
        raise SystemExit(f"No APS URN in cache for {ARQ_FILE}")
    urn, _record_dir, _object_key = record

    out_dir = job_dir / "plan_rendered_coord_trace"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = ARQ_FILE.replace(" ", "_").replace(".", "_")
    pages = render_plan_pages(
        urn=urn,
        aps_token=aps_token,
        clashes=clashes,
        output_dir=str(out_dir),
        stem=stem,
        timeout_s=180,
    )
    if not pages:
        raise SystemExit("viewer-engine returned no pages")

    plan_margin = 10.0
    plan_frame_bottom = 22.1 + 4.0
    plan_w = 792.0 - 2 * plan_margin
    plan_h = (612.0 - plan_margin) - plan_frame_bottom
    _scaled_image_path(pages[0], plan_w, plan_h)
    return pages[0]


def main() -> int:
    _setup_logging()
    job_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_JOB
    if not job_dir.is_dir():
        raise SystemExit(f"Job dir not found: {job_dir}")

    incident = _load_incident(job_dir)
    print(f"COORD trace job_dir={job_dir}")
    print(f"COORD trace correlation_id={job_dir.name}")
    print(f"COORD trace incident={TARGET_INCIDENT}")

    _run_extraction(job_dir, incident)
    _run_clash(job_dir, incident)

    aps_token = _get_aps_token()
    page = _run_viewer_and_pdf(job_dir, incident, aps_token)
    print(f"COORD trace plan_page={page}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
