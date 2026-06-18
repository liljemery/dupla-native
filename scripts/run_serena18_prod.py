#!/usr/bin/env python3
"""
Prueba de producción — pipeline clash identification SERENA 18
5 disciplinas, DWGs más recientes. Endpoints reales del backend.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

BASE_URL  = "http://127.0.0.1:8000"
EMAIL     = "master@dupla.demo"
PASSWORD  = "master123"

SERENA_ROOT = Path("/Users/samuelfernandez/Downloads/SERENA 18/PLANOS RECIBIDOS")

TEST_FILES = [
    {
        "path": SERENA_ROOT / "ARQUITECTONICOS/11. NOVIEMBRE 2023/DWG/REFERENCE DETAIL PLAN/2208-Serena18-ID-Base.dwg",
        "discipline": "arquitectura",
        "label": "ARQ — ID Base (Nov 2023)",
    },
    {
        "path": SERENA_ROOT / "TECNICOS/ESTRUCTURAL/01. ENERO 2023/EST. SERENA 18 - E09 - PLANTA EST. LOSAS DE PISO SOBRE TERRENO  Y DETALLES  CASA.dwg",
        "discipline": "estructura",
        "label": "EST — Losas de piso (Ene 2023)",
    },
    {
        "path": SERENA_ROOT / "TECNICOS/ELECTRICOS/11. NOVIEMBRE 2024/20.01.2025 SERENA 18 PLANOS ELECTRICOS FINALES (MAVA).dwg",
        "discipline": "electrica",
        "label": "ELC — Finales MAVA (Ene 2025)",
    },
    {
        "path": SERENA_ROOT / "TECNICOS/MECANICOS/09. SEPTIEMBRE 2024/27.09.2024 SE 18 PLANTA MECANICA FINALES.dwg",
        "discipline": "mecanica",
        "label": "MEC — Mecánica finales (Sep 2024)",
    },
    {
        "path": SERENA_ROOT / "TECNICOS/HIDROSANITARIOS/07. JULIO 2025/5.7.2025 SERENA 18 PLANOS AS-BUILT.dwg",
        "discipline": "plomeria",
        "label": "HID — As-built (Jul 2025)",
    },
]

REPORT_OUT    = Path("/tmp/serena18_prod_clash_report.json")
POLL_INTERVAL = 15
POLL_TIMEOUT  = 2400

def ok(msg):   print(f"  ✓ {msg}")
def step(msg): print(f"\n── {msg}")
def fail(msg): print(f"  ✗ {msg}"); sys.exit(1)


def login() -> dict:
    step("1. Login")
    r = requests.post(f"{BASE_URL}/api/auth/token",
                      data={"username": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        fail(f"Login falló {r.status_code}: {r.text}")
    token = r.json()["access_token"]
    ok(f"Token obtenido ({EMAIL})")
    return {"Authorization": f"Bearer {token}"}


def create_project(headers) -> str:
    step("2. Crear proyecto")
    r = requests.post(f"{BASE_URL}/api/projects", headers=headers,
                      data={"name": "SERENA 18 — Prod 5 disciplinas", "project_kind": "CLIENT"})
    if r.status_code not in (200, 201):
        fail(f"Crear proyecto falló {r.status_code}: {r.text}")
    uuid = r.json()["uuid"]
    ok(f"Proyecto creado: {uuid}")
    return uuid


def create_folder(headers, project_uuid) -> str:
    step("3. Crear carpeta PLANOS RECIBIDOS")
    r = requests.post(f"{BASE_URL}/api/projects/{project_uuid}/file-folders",
                      headers=headers, json={"name": "PLANOS RECIBIDOS"})
    if r.status_code not in (200, 201):
        fail(f"Crear carpeta falló {r.status_code}: {r.text}")
    data = r.json()
    # key puede ser uuid o id según el endpoint
    folder_uuid = data.get("uuid") or data.get("id")
    ok(f"Carpeta creada: {folder_uuid}")
    return folder_uuid


def upload_and_tag(headers, project_uuid, folder_uuid) -> None:
    step("4. Subir DWGs y asignar disciplinas")
    for entry in TEST_FILES:
        path: Path = entry["path"]
        with path.open("rb") as fh:
            r = requests.post(
                f"{BASE_URL}/api/projects/{project_uuid}/files",
                headers=headers,
                data={"folder_id": folder_uuid},
                files={"file": (path.name, fh, "application/octet-stream")},
            )
        if r.status_code not in (200, 201):
            fail(f"Upload falló ({path.name}) {r.status_code}: {r.text}")
        file_data = r.json()
        file_uuid = file_data.get("uuid") or file_data.get("id")

        r2 = requests.patch(
            f"{BASE_URL}/api/projects/{project_uuid}/files/{file_uuid}",
            headers=headers,
            json={"discipline": entry["discipline"]},
        )
        if r2.status_code not in (200, 201):
            fail(f"Tag disciplina falló ({path.name}) {r2.status_code}: {r2.text}")

        ok(f"{entry['label']}  →  {entry['discipline']}  [{file_uuid}]")


def verify_inventory(headers, project_uuid, folder_uuid) -> None:
    step("5. Verificar inventario")
    r = requests.get(
        f"{BASE_URL}/api/projects/{project_uuid}/coordination/inventory",
        params={"folder_uuid": folder_uuid},
        headers=headers,
    )
    if r.status_code != 200:
        fail(f"Inventario falló {r.status_code}: {r.text}")
    inv = r.json()
    ok(f"ready={inv.get('ready')}  disciplinas={inv.get('summary', {}).get('discipline_count')}")
    for b in (inv.get("blockers") or []):
        print(f"     ⚠ blocker: {b}")


def enqueue_job(headers, project_uuid, folder_uuid) -> None:
    step("6. Encolar clash job")
    r = requests.post(
        f"{BASE_URL}/api/projects/{project_uuid}/clash/jobs",
        headers=headers,
        json={"folder_uuid": folder_uuid},
    )
    if r.status_code not in (200, 201, 202):
        fail(f"Enqueue falló {r.status_code}: {r.text}")
    data = r.json()
    ok(f"Job encolado: id={data.get('id') or data.get('uuid')}  status={data.get('status')}")


def poll_job(headers, project_uuid) -> None:
    step("7. Polling hasta completar")
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        r = requests.get(
            f"{BASE_URL}/api/projects/{project_uuid}/clash/jobs/latest",
            headers=headers,
        )
        if r.status_code != 200:
            fail(f"Poll falló {r.status_code}: {r.text}")
        data   = r.json()
        status = data.get("status")
        print(f"     status={status}")
        if status == "completed":
            ok("Job completado")
            return
        if status in ("failed", "error"):
            fail(f"Job terminó con error: {json.dumps(data, indent=2)}")
        time.sleep(POLL_INTERVAL)
    fail(f"Timeout — job no completó en {POLL_TIMEOUT}s")


def get_report(headers, project_uuid) -> None:
    step("8. Obtener reporte de coordinación")
    r = requests.get(
        f"{BASE_URL}/api/projects/{project_uuid}/clash/jobs/latest",
        headers=headers,
    )
    if r.status_code != 200:
        fail(f"Reporte falló {r.status_code}: {r.text}")
    report  = r.json()
    summary = report.get("summary", {})
    clashes = report.get("clashes", [])
    docs    = report.get("analyzed_documents", [])

    ok(f"run_status={report.get('run_status')}  analysis_mode={report.get('analysis_mode')}")
    ok(f"errors={summary.get('errors')}  warnings={summary.get('warnings')}  ok={summary.get('ok')}")
    ok(f"clashes={len(clashes)}  docs={len(docs)}")

    if docs:
        print("\n  Documentos analizados:")
        for d in docs:
            print(f"    - {d.get('file_name')} [{d.get('discipline_label')}]"
                  f"  status={d.get('status')}  elements={d.get('element_count', '?')}")

    if clashes:
        top = min(len(clashes), 15)
        print(f"\n  Primeras {top} incidencias (de {len(clashes)} total):")
        for c in clashes[:top]:
            print(f"    [{c.get('severity','?')}] {c.get('clash_kind','?')}: "
                  f"{c.get('discipline_a')} vs {c.get('discipline_b')} ({c.get('level_id','?')})")

    REPORT_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ok(f"Reporte completo → {REPORT_OUT}")


def main():
    print("=" * 62)
    print("  SERENA 18 — Pipeline producción clash identification")
    print("  5 disciplinas — DWGs más recientes por disciplina")
    print("=" * 62)

    missing = [e["path"] for e in TEST_FILES if not e["path"].is_file()]
    if missing:
        print("\n⚠ Archivos no encontrados:")
        for p in missing: print(f"  {p}")
        sys.exit(1)

    print("\n  Archivos a procesar:")
    for e in TEST_FILES:
        size_mb = e["path"].stat().st_size / 1_048_576
        print(f"  • {e['label']}  ({size_mb:.1f} MB)")

    headers      = login()
    project_uuid = create_project(headers)
    folder_uuid  = create_folder(headers, project_uuid)
    upload_and_tag(headers, project_uuid, folder_uuid)
    verify_inventory(headers, project_uuid, folder_uuid)
    enqueue_job(headers, project_uuid, folder_uuid)
    poll_job(headers, project_uuid)
    get_report(headers, project_uuid)

    print("\n" + "=" * 62)
    print("  Pipeline completado exitosamente ✓")
    print("=" * 62)


if __name__ == "__main__":
    main()
