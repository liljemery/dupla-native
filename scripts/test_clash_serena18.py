#!/usr/bin/env python3
"""
Smoke-test del pipeline completo de clash identification con planos reales de SERENA 18.
Usa smoke mode (sin motor Dupla) para validar la integración end-to-end.

Uso:
    python scripts/test_clash_serena18.py

Requiere backend en :8000 y coordination-service en :8002 corriendo localmente.
"""

import json
import sys
import time
from pathlib import Path

import requests

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_URL = "http://127.0.0.1:8000"
EMAIL = "master@dupla.demo"
PASSWORD = "master123"

SERENA_ROOT = Path("/Users/samuelfernandez/Downloads/SERENA 18/PLANOS RECIBIDOS")

# Un DWG representativo por disciplina (el más reciente / final de cada una)
TEST_FILES = [
    {
        "path": SERENA_ROOT / "ARQUITECTONICOS/06. JUNIO 2024/2208-Serena18-ID-Base.dwg",
        "discipline": "arquitectura",
        "label": "ARQ — Planta base",
    },
    {
        "path": SERENA_ROOT / "TECNICOS/ESTRUCTURAL/01. ENERO 2023/EST. SERENA 18 - E09 - PLANTA EST. LOSAS DE PISO SOBRE TERRENO  Y DETALLES  CASA.dwg",
        "discipline": "estructura",
        "label": "EST — Losas de piso",
    },
    {
        "path": SERENA_ROOT / "TECNICOS/ELECTRICOS/11. NOVIEMBRE 2024/20.01.2025 SERENA 18 PLANOS ELECTRICOS FINALES (MAVA).dwg",
        "discipline": "electrica",
        "label": "ELC — Planos eléctricos finales",
    },
    {
        "path": SERENA_ROOT / "TECNICOS/MECANICOS/09. SEPTIEMBRE 2024/27.09.2024 SE 18 PLANTA MECANICA FINALES.dwg",
        "discipline": "mecanica",
        "label": "MEC — Planta mecánica final",
    },
]

POLL_INTERVAL = 10   # segundos entre polls
POLL_TIMEOUT  = 900  # 15 min — APS puede tardar hasta 5 min por DWG


# ── Helpers ────────────────────────────────────────────────────────────────────
def ok(msg: str) -> None:
    print(f"  ✓ {msg}")

def fail(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)
    sys.exit(1)

def step(msg: str) -> None:
    print(f"\n── {msg}")


# ── Pasos ──────────────────────────────────────────────────────────────────────
def login() -> dict:
    step("1. Login")
    r = requests.post(
        f"{BASE_URL}/api/auth/token",
        data={"username": EMAIL, "password": PASSWORD},
    )
    if r.status_code != 200:
        fail(f"Login falló {r.status_code}: {r.text}")
    data = r.json()
    token = data.get("access_token")
    if not token:
        fail(f"No access_token en respuesta: {data}")
    ok(f"Token obtenido ({EMAIL})")
    return {"Authorization": f"Bearer {token}"}


def create_project(headers: dict) -> str:
    step("2. Crear proyecto SERENA 18")
    r = requests.post(
        f"{BASE_URL}/api/projects",
        data={"name": "SERENA 18 — Test Clashes", "project_kind": "CLIENT"},
        headers=headers,
    )
    if r.status_code not in (200, 201):
        fail(f"Crear proyecto falló {r.status_code}: {r.text}")
    uuid = r.json()["uuid"]
    ok(f"Proyecto creado: {uuid}")
    return uuid


def create_folder(headers: dict, project_uuid: str) -> str:
    step("3. Crear carpeta PLANOS RECIBIDOS")
    r = requests.post(
        f"{BASE_URL}/api/projects/{project_uuid}/file-folders",
        json={"name": "PLANOS RECIBIDOS", "parent_uuid": None},
        headers=headers,
    )
    if r.status_code not in (200, 201):
        fail(f"Crear carpeta falló {r.status_code}: {r.text}")
    uuid = r.json()["uuid"]
    ok(f"Carpeta creada: {uuid}")
    return uuid


def upload_and_tag_files(headers: dict, project_uuid: str, folder_uuid: str) -> list[str]:
    step("4. Subir DWGs y asignar disciplinas")
    file_uuids = []

    for entry in TEST_FILES:
        path = entry["path"]
        if not path.is_file():
            fail(f"Archivo no encontrado: {path}")

        # Upload
        with open(path, "rb") as fh:
            r = requests.post(
                f"{BASE_URL}/api/projects/{project_uuid}/files",
                headers=headers,
                files={"file": (path.name, fh, "application/octet-stream")},
                data={"folder_uuid": folder_uuid},
            )
        if r.status_code not in (200, 201):
            fail(f"Upload falló ({path.name}) {r.status_code}: {r.text[:300]}")

        file_uuid = r.json()["uuid"]

        # Asignar disciplina
        r2 = requests.patch(
            f"{BASE_URL}/api/projects/{project_uuid}/files/{file_uuid}",
            json={"discipline": entry["discipline"]},
            headers=headers,
        )
        if r2.status_code not in (200, 201):
            fail(f"Patch disciplina falló ({path.name}) {r2.status_code}: {r2.text[:300]}")

        ok(f"{entry['label']}  →  discipline={entry['discipline']}  uuid={file_uuid}")
        file_uuids.append(file_uuid)

    return file_uuids


def enqueue_job(headers: dict, project_uuid: str, folder_uuid: str) -> str:
    step("5. Encolar clash job")
    r = requests.post(
        f"{BASE_URL}/api/projects/{project_uuid}/clash/jobs",
        json={"folder_uuid": folder_uuid},
        headers=headers,
    )
    if r.status_code not in (200, 201, 202):
        fail(f"Enqueue falló {r.status_code}: {r.text}")
    data = r.json()
    ok(f"Job encolado: id={data['id']}  job_id={data['job_id']}  status={data['status']}")
    return data["id"]


def poll_job(headers: dict, project_uuid: str) -> dict:
    step("6. Polling hasta completar")
    deadline = time.time() + POLL_TIMEOUT
    last_status = None
    while time.time() < deadline:
        r = requests.get(
            f"{BASE_URL}/api/projects/{project_uuid}/clash/jobs/latest",
            headers=headers,
        )
        if r.status_code != 200:
            fail(f"Poll falló {r.status_code}: {r.text}")
        data = r.json()
        status = data["status"]
        if status != last_status:
            print(f"     status={status}")
            last_status = status
        if status == "completed":
            ok("Job completado")
            return data
        if status == "failed":
            fail(f"Job falló: {data.get('error')}")
        time.sleep(POLL_INTERVAL)
    fail(f"Timeout esperando el job ({POLL_TIMEOUT}s)")


def get_report(headers: dict, project_uuid: str) -> None:
    step("7. Obtener reporte de coordinación")
    r = requests.get(
        f"{BASE_URL}/api/projects/{project_uuid}/structural-analysis-report",
        headers=headers,
    )
    if r.status_code != 200:
        fail(f"Reporte falló {r.status_code}: {r.text}")
    report = r.json()

    run_status = report.get("run_status")
    summary    = report.get("summary", {})
    clashes    = report.get("clashes", [])
    docs       = report.get("analyzed_documents", [])

    ok(f"run_status={run_status}")
    ok(f"summary    errors={summary.get('errors')} warnings={summary.get('warnings')} ok={summary.get('ok')}")
    ok(f"clashes    {len(clashes)} incidencia(s)")
    ok(f"docs       {len(docs)} documento(s) analizados")

    if clashes:
        print("\n  Primeras incidencias:")
        for c in clashes[:3]:
            print(f"    [{c.get('priority')}] {c.get('title')}")
            print(f"           {c.get('description', '')[:100]}")

    print("\n  JSON completo del reporte guardado en /tmp/serena18_clash_report.json")
    Path("/tmp/serena18_clash_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 60)
    print("  SERENA 18 — Test pipeline clash identification")
    print("=" * 60)

    # Verificar que los archivos existen antes de empezar
    missing = [e["path"] for e in TEST_FILES if not e["path"].is_file()]
    if missing:
        print("Archivos no encontrados:")
        for p in missing:
            print(f"  {p}")
        sys.exit(1)

    headers = login()
    project_uuid = create_project(headers)
    folder_uuid  = create_folder(headers, project_uuid)
    upload_and_tag_files(headers, project_uuid, folder_uuid)
    enqueue_job(headers, project_uuid, folder_uuid)
    poll_job(headers, project_uuid)
    get_report(headers, project_uuid)

    print("\n" + "=" * 60)
    print("  Pipeline completado exitosamente")
    print("=" * 60)


if __name__ == "__main__":
    main()
