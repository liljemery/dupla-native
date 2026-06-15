#!/usr/bin/env python3
"""
Genera el PDF checklist GA-FO-08 de Serena 18 directamente,
usando el output de clash ya calculado (sin re-correr el motor).

Uso:
    PYTHONPATH=/Users/samuelfernandez/dupla-1/backend \
    python scripts/gen_pdf_serena18.py [job_dir]

Si no se indica job_dir, busca el output más reciente con incidencias en /tmp/dupla-coord-output.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# ── Configuración ──────────────────────────────────────────────────────────────
CLIENT_ID     = os.getenv("CLIENT_ID",     "Oi9sCuGDQo8Xq52bwJOm9vdK1lQGKh7szRoes0oij016wGox")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "ubHMOGOkeSe39DPH8FG4PL04bGRONdHSKugUsFjqVHMmveQjSt6oPhafGewQfnu8")
PROJECT_NAME  = "SERENA 18"
OUT_PDF       = Path("/tmp/serena18_checklist.pdf")

# ── Helpers ────────────────────────────────────────────────────────────────────

def _find_best_job() -> Path | None:
    root = Path("/tmp/dupla-coord-output")
    if not root.is_dir():
        return None
    best = None
    best_count = 0
    for d in root.iterdir():
        pi = d / "primary_incidents.json"
        if not pi.is_file():
            continue
        try:
            data = json.loads(pi.read_text())
            n = data.get("incident_count", 0)
            if n > best_count:
                best_count = n
                best = d
        except Exception:
            pass
    return best


def _get_aps_token() -> str:
    import requests as req
    r = req.post(
        "https://developer.api.autodesk.com/authentication/v2/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials",
            "scope": "data:read viewables:read",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    # 1. Localizar el job dir
    job_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _find_best_job()
    if not job_dir or not job_dir.is_dir():
        sys.exit(f"No se encontró un job dir válido. Pasa uno como argumento.")
    print(f"Job dir: {job_dir}")

    # 2. Cargar incidencias
    pi_path = job_dir / "primary_incidents.json"
    incidents_data = json.loads(pi_path.read_text())
    incidents = incidents_data.get("incidents", [])
    print(f"Incidencias: {len(incidents)}")

    # 3. Cargar file_discipline_hints desde structural_analysis_report
    sar_path = job_dir / "structural_analysis_report.json"
    hints: dict[str, str] = {}
    if sar_path.is_file():
        sar = json.loads(sar_path.read_text())
        for doc in sar.get("analyzed_documents", []):
            fname = doc.get("file_name") or doc.get("filename") or doc.get("name", "")
            disc  = doc.get("discipline_label") or doc.get("discipline", "")
            if fname and disc:
                hints[fname] = disc
    print(f"Disciplinas detectadas: {hints}")

    # 4. Obtener APS token
    print("Obteniendo APS token…")
    try:
        aps_token = _get_aps_token()
        print("  Token OK")
    except Exception as exc:
        print(f"  APS token falló: {exc} — continuando sin imágenes reales")
        aps_token = None

    # 5. Generar PDF
    print("Generando PDF…")
    t0 = time.time()

    from app.services.clash_reports.checklist_pdf import build_checklist_pdf

    logo_path = str(
        Path(__file__).resolve().parents[1]
        / "backend/app/services/clash_reports/assets/grupo-dupla-logo.png"
    )

    pdf_bytes = build_checklist_pdf(
        incidents=incidents,
        project_name=PROJECT_NAME,
        checklist_number=None,
        reviewer_name="Revisión Técnica",
        export_date=None,
        logo_grupodupla_path=logo_path if Path(logo_path).is_file() else None,
        logo_constructora_path=None,
        aps_token=aps_token,
        job_cache_dir=str(job_dir),
        file_discipline_hints=hints,
    )

    OUT_PDF.write_bytes(pdf_bytes)
    elapsed = time.time() - t0
    print(f"\n✓ PDF generado en {elapsed:.1f}s → {OUT_PDF}  ({len(pdf_bytes):,} bytes)")
    print(f"  open {OUT_PDF}")


if __name__ == "__main__":
    main()
