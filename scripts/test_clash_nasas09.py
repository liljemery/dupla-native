#!/usr/bin/env python3
"""
E2E: pipeline clash + export GA-FO-08 con planos reales LAS NASAS 09.

Uso:
    python scripts/test_clash_nasas09.py
    python scripts/test_clash_nasas09.py --rerun   # segunda corrida (caché APS)

Requiere backend :8000 y coordination-service :8002 (./scripts/dev.sh start).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import NoReturn

import requests

BASE_URL = "http://127.0.0.1:8000"
EMAIL = "master@dupla.demo"
PASSWORD = "master123"

DOWNLOADS = Path(
    os.environ.get(
        "NASAS09_DOWNLOADS",
        "/Users/thewizard/Downloads/NASAS 9 DUPLA",
    )
)

TEST_FILES = [
    {
        "path": DOWNLOADS / "ARQUITECTONICO" / "PLANOS ARQ.-LAS NASAS 09-20260320.dwg",
        "discipline": "arquitectura",
        "label": "ARQ — Planos arquitectónicos",
    },
    {
        "path": DOWNLOADS / "ESTRUCTURAL" / "20.03.2026 LAS NASAS 09 ES-05@11- PLANTAS ENTREPISO-LAS NASAS-DESSANGLES.dwg",
        "discipline": "estructura",
        "label": "EST — Plantas entrepiso",
    },
    {
        "path": DOWNLOADS / "ELECTRICO" / "20.03.2026 LAS NASAS 09-PLANOS ELECTRICOS .dwg",
        "discipline": "electrica",
        "label": "ELC — Planos eléctricos",
    },
    {
        "path": DOWNLOADS / "SANITARIO" / "15.04.2026 LAS NASAS 09 HS-AGUA POTABLE.dwg",
        "discipline": "plomeria",
        "label": "SAN — Agua potable",
    },
]

POLL_INTERVAL = 10
POLL_TIMEOUT_FIRST = 10800  # 3h: SVF1 + volcado Viewer por 4 DWG grandes
POLL_TIMEOUT_CACHE = 3600  # rerun con caché viewer; ELC puede re-traducirse (~20 min)
STATE_FILE = Path("/tmp/nasas09_e2e_state.json")
OUT_PDF = Path("/tmp/nasas09_ga_fo08.pdf")
OUT_REPORT = Path("/tmp/nasas09_clash_report.json")

_PROJECT_NAME = "LAS NASAS 09 — Test Clashes 4 planos"


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def fail(msg: str) -> NoReturn:
    print(f"  ✗ {msg}", file=sys.stderr)
    sys.exit(1)


def step(msg: str) -> None:
    print(f"\n── {msg}")


def save_state(project_uuid: str, folder_uuid: str) -> None:
    STATE_FILE.write_text(
        json.dumps({"project_uuid": project_uuid, "folder_uuid": folder_uuid}, indent=2),
        encoding="utf-8",
    )


def load_state() -> tuple[str, str] | None:
    if not STATE_FILE.is_file():
        return None
    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    pu, fu = data.get("project_uuid"), data.get("folder_uuid")
    if pu and fu:
        return str(pu), str(fu)
    return None


def warn_aps_issues(report: dict) -> None:
    docs = report.get("analyzed_documents") or []
    zero_elems = [d.get("file_name") for d in docs if int(d.get("element_count") or 0) == 0]
    if zero_elems and not (report.get("clashes") or []):
        print(
            "\n  ⚠ Sin clashes: extracción APS devolvió 0 elementos. "
            "Configure CLIENT_ID y CLIENT_SECRET en backend/.env.",
            file=sys.stderr,
        )


def login() -> dict:
    step("1. Login")
    r = requests.post(
        f"{BASE_URL}/api/auth/token",
        data={"username": EMAIL, "password": PASSWORD},
    )
    if r.status_code != 200:
        fail(f"Login falló {r.status_code}: {r.text}")
    token = r.json().get("access_token")
    if not token:
        fail("Sin access_token")
    ok(f"Token obtenido ({EMAIL})")
    return {"Authorization": f"Bearer {token}"}


def create_project(headers: dict) -> str:
    step("2. Crear proyecto NASAS 09")
    r = requests.post(
        f"{BASE_URL}/api/projects",
        data={"name": _PROJECT_NAME, "project_kind": "CLIENT"},
        headers=headers,
    )
    if r.status_code not in (200, 201):
        fail(f"Crear proyecto falló {r.status_code}: {r.text}")
    uuid = r.json()["uuid"]
    ok(f"Proyecto: {uuid}")
    return uuid


def create_folder(headers: dict, project_uuid: str) -> str:
    step("3. Carpeta PLANOS RECIBIDOS")
    r = requests.post(
        f"{BASE_URL}/api/projects/{project_uuid}/file-folders",
        json={"name": "PLANOS RECIBIDOS", "parent_uuid": None},
        headers=headers,
    )
    if r.status_code not in (200, 201):
        fail(f"Crear carpeta falló {r.status_code}: {r.text}")
    uuid = r.json()["uuid"]
    ok(f"Carpeta: {uuid}")
    return uuid


def upload_and_tag(headers: dict, project_uuid: str, folder_uuid: str) -> None:
    step("4. Subir DWG y disciplinas")
    for entry in TEST_FILES:
        path = entry["path"]
        with open(path, "rb") as fh:
            r = requests.post(
                f"{BASE_URL}/api/projects/{project_uuid}/files",
                headers=headers,
                files={"file": (path.name, fh, "application/octet-stream")},
                data={"folder_uuid": folder_uuid},
            )
        if r.status_code not in (200, 201):
            fail(f"Upload {path.name}: {r.status_code} {r.text[:300]}")
        file_uuid = r.json()["uuid"]
        r2 = requests.patch(
            f"{BASE_URL}/api/projects/{project_uuid}/files/{file_uuid}",
            json={"discipline": entry["discipline"]},
            headers=headers,
        )
        if r2.status_code not in (200, 201):
            fail(f"Disciplina {path.name}: {r2.status_code}")
        ok(entry["label"])


def enqueue(headers: dict, project_uuid: str, folder_uuid: str) -> None:
    step("5. Encolar clash job")
    r = requests.post(
        f"{BASE_URL}/api/projects/{project_uuid}/clash/jobs",
        json={"folder_uuid": folder_uuid},
        headers=headers,
    )
    if r.status_code not in (200, 201, 202):
        fail(f"Enqueue: {r.status_code} {r.text}")
    ok(f"Job id={r.json().get('id')} status={r.json().get('status')}")


def poll(headers: dict, project_uuid: str, *, timeout: int) -> float:
    step("6. Polling job")
    deadline = time.time() + timeout
    started = time.time()
    last_status = None
    while time.time() < deadline:
        r = requests.get(
            f"{BASE_URL}/api/projects/{project_uuid}/clash/jobs/latest",
            headers=headers,
        )
        if r.status_code != 200:
            fail(f"Poll: {r.status_code}")
        data = r.json()
        status = data["status"]
        progress = data.get("progress") or {}
        if status != last_status:
            print(f"     status={status}")
            last_status = status
        if progress.get("total"):
            print(
                f"     progress={progress.get('processed', 0)}/{progress.get('total')} "
                f"phase={progress.get('phase')} elapsed={progress.get('elapsed_s')}s"
            )
        if status == "completed":
            elapsed = round(time.time() - started, 1)
            ok(f"Completado en {elapsed}s (límite {timeout}s)")
            return elapsed
        if status == "failed":
            fail(f"Job falló: {data.get('error')}")
        time.sleep(POLL_INTERVAL)
    fail(f"Timeout {timeout}s")
    return 0.0


def fetch_report(headers: dict, project_uuid: str, elapsed: float) -> dict:
    step("7. Reporte estructural")
    r = requests.get(
        f"{BASE_URL}/api/projects/{project_uuid}/structural-analysis-report",
        headers=headers,
    )
    if r.status_code != 200:
        fail(f"Reporte: {r.status_code}")
    report = r.json()
    clashes = report.get("clashes") or []
    ok(f"clashes={len(clashes)} benchmark_elapsed_s={elapsed}")
    warn_aps_issues(report)
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ok(f"JSON → {OUT_REPORT}")
    return report


def download_ga_fo08(headers: dict, project_uuid: str) -> None:
    step("8. Descargar GA-FO-08 (final-human.pdf)")
    r = requests.get(
        f"{BASE_URL}/api/projects/{project_uuid}/clash/jobs/latest/exports/final-human.pdf",
        headers=headers,
    )
    if r.status_code != 200:
        fail(f"Export PDF: {r.status_code} {r.text[:500]}")
    OUT_PDF.write_bytes(r.content)
    ok(f"PDF {len(r.content):,} bytes → {OUT_PDF}")
    disp = r.headers.get("Content-Disposition", "")
    if disp:
        print(f"     Content-Disposition: {disp}")


def validate_pdf() -> None:
    step("9. Validar estructura GA-FO-08")
    script = Path(__file__).resolve().parent / "validate_ga_fo08_pdf.py"
    import subprocess

    proc = subprocess.run(
        [sys.executable, str(script), str(OUT_PDF)],
        capture_output=True,
        text=True,
    )
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        fail("Validación GA-FO-08 falló")
    ok("Estructura GA-FO-08 OK")


def validate_geometry_acceptance(report: dict, pdf_bytes: int) -> None:
    """Criterios Plan A (NASAS 09 geometría exacta)."""
    step("10. Criterios geometría Plan A")
    docs = report.get("analyzed_documents") or []
    dwg_docs = [d for d in docs if str(d.get("file_name") or "").lower().endswith(".dwg")]
    exact_docs = [
        d
        for d in dwg_docs
        if d.get("geometry_quality") == "exact"
        or str(d.get("aps_result") or "") in {"viewer_geometry", "viewer_cache"}
    ]
    with_viewer = [d for d in dwg_docs if int(d.get("viewer_elements") or 0) > 0]
    ok(f"DWG con geometría exacta: {len(exact_docs)}/{len(dwg_docs)}")
    ok(f"DWG con viewer_elements>0: {len(with_viewer)}/{len(dwg_docs)}")
    if len(with_viewer) < len(dwg_docs):
        names = [d.get("file_name") for d in dwg_docs if int(d.get("viewer_elements") or 0) <= 0]
        fail(f"Faltan viewer_elements en: {names}")

    clashes = report.get("clashes") or []
    if not clashes:
        fail("Se esperaban clashes > 0 con caché APS")
    san_dwg_pairs = [
        c
        for c in clashes
        if any("san" in (d or "").lower() or "agua" in (d or "").lower() for d in (c.get("disciplines") or []))
        and any("eléct" in (d or "").lower() or "elect" in (d or "").lower() for d in (c.get("disciplines") or []))
    ]
    if san_dwg_pairs:
        ok(f"Par SAN↔ELC detectado ({len(san_dwg_pairs)} clash(es))")
    else:
        print("  ⚠ No se encontró clash SAN↔ELC explícito; revise descripciones/disciplinas")

    pdf_only_plumbing = [
        c
        for c in clashes
        if (c.get("geometry_sources") or "").lower() == "pdf_companion_vector"
        and any("fontan" in (d or "").lower() or "plom" in (d or "").lower() for d in (c.get("disciplines") or []))
    ]
    if pdf_only_plumbing:
        fail(f"Fontanería solo pdf_companion_vector: {len(pdf_only_plumbing)} incidente(s)")

    if pdf_bytes < 100_000:
        fail(f"GA-FO-08 demasiado pequeño: {pdf_bytes} bytes")
    ok(f"GA-FO-08 ≥ 100 KB ({pdf_bytes:,} bytes)")
    ok("Criterios Plan A OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rerun",
        action="store_true",
        help="Segunda corrida (benchmark caché, límite 300s)",
    )
    args = parser.parse_args()
    timeout = POLL_TIMEOUT_CACHE if args.rerun else POLL_TIMEOUT_FIRST

    print("=" * 60)
    print("  LAS NASAS 09 — E2E clash + GA-FO-08")
    print("=" * 60)

    missing = [str(e["path"]) for e in TEST_FILES if not e["path"].is_file()]
    if missing:
        print("Archivos no encontrados:")
        for p in missing:
            print(f"  {p}")
        sys.exit(1)

    headers = login()
    if args.rerun:
        state = load_state()
        if not state:
            fail("Sin estado previo en /tmp/nasas09_e2e_state.json — ejecuta sin --rerun primero")
        project_uuid, folder_uuid = state
        ok(f"Reutilizando proyecto {project_uuid}")
        enqueue(headers, project_uuid, folder_uuid)
    else:
        project_uuid = create_project(headers)
        folder_uuid = create_folder(headers, project_uuid)
        upload_and_tag(headers, project_uuid, folder_uuid)
        save_state(project_uuid, folder_uuid)
        enqueue(headers, project_uuid, folder_uuid)
    elapsed = poll(headers, project_uuid, timeout=timeout)
    report = fetch_report(headers, project_uuid, elapsed)
    download_ga_fo08(headers, project_uuid)
    validate_pdf()
    validate_geometry_acceptance(report, OUT_PDF.stat().st_size if OUT_PDF.is_file() else 0)

    print("\n" + "=" * 60)
    print(f"  E2E OK — {elapsed}s — {OUT_PDF}")
    print("=" * 60)


if __name__ == "__main__":
    main()
