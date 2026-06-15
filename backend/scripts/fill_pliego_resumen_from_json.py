#!/usr/bin/env python3
"""
Rellena la hoja RESUMEN del GA-FO-01 (columna A = N.º, D = Estado, F = Observaciones)
desde un JSON con el mismo formato que guarda la app en `specifications_document.ga_fo_01_arquitectura`.

Ejemplos:

  # Objeto completo (como en la API)
  python scripts/fill_pliego_resumen_from_json.py \\
    --template "../docs/provided_docs/GA-FO-01-(06-2025)-V02- Pliego de Condiciones - Arquitectura.xlsx" \\
    --json pliego-snapshot.json \\
    --out Pliego_Actualizado.xlsx

  # Solo item_states
  echo '{"2.1.":{"estado":"COMPLETO","notas":"Listo"}}' | python scripts/fill_pliego_resumen_from_json.py -t plantilla.xlsx -o out.xlsx --stdin
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ejecutar desde directorio `backend/`
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from openpyxl import load_workbook  # noqa: E402

from app.services.pliego_template_fill import (  # noqa: E402
    fill_resumen_pliego_ga_fo_01,
    resolve_pliego_template_path,
)


def _load_item_states(raw: dict) -> dict:
    if "item_states" in raw and isinstance(raw["item_states"], dict):
        return dict(raw["item_states"])
    return dict(raw)


def main() -> None:
    p = argparse.ArgumentParser(description="Rellena RESUMEN del Excel GA-FO-01 desde JSON.")
    p.add_argument("--template", "-t", type=Path, help="Ruta al .xlsx plantilla (opcional si está en app/templates o docs/provided_docs)")
    p.add_argument("--json", "-j", type=Path, help="Archivo JSON")
    p.add_argument("--stdin", action="store_true", help="Leer JSON desde stdin")
    p.add_argument("--out", "-o", type=Path, default=Path("Pliego_Actualizado.xlsx"))
    args = p.parse_args()

    if args.stdin:
        data = json.load(sys.stdin)
    elif args.json:
        data = json.loads(args.json.read_text(encoding="utf-8"))
    else:
        p.error("Indica --json o --stdin")

    item_states = _load_item_states(data)

    tpl: Path | None = args.template
    if tpl is None:
        resolved = resolve_pliego_template_path(Path("app/templates"))
        if resolved is None:
            sys.exit("No se encontró plantilla. Usa --template o copia el GA-FO-01 a backend/app/templates/.")
        tpl = resolved
    if not tpl.is_file():
        sys.exit(f"No existe la plantilla: {tpl}")

    out = args.out.resolve()
    tpl_abs = tpl.resolve()
    if out == tpl_abs:
        sys.exit(
            "El archivo de salida no puede ser la misma ruta que la plantilla. "
            "Usa p. ej. --out Pliego_Actualizado.xlsx para generar un archivo nuevo sin tocar el original."
        )

    wb = load_workbook(tpl)
    if not fill_resumen_pliego_ga_fo_01(wb, item_states):
        sys.exit("No se escribió ninguna fila (¿item_states vacío o hoja RESUMEN ausente?).")

    wb.save(out)
    print(f"OK: {out}")


if __name__ == "__main__":
    main()
