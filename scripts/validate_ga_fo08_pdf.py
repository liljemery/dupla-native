#!/usr/bin/env python3
"""Validate GA-FO-08 PDF structure against the reference checklist format."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED_STRINGS = [
    "GESTIÓN DE ARQUITECTURA Y CONTROL DE PLANOS",
    "LISTA DE CHEQUEO",
    "DISCIPLINA",
    "NÚMERO DE PLANO",
    "TÍTULO DEL PLANO",
    "DESCRIPCIÓN DE PLANOS",
    "FECHA DEL PLANO",
    "REVISIÓN",
    "CORRELACIÓN CON",
    "OBSERVACIONES",
    "GA-FO-08 (04.2025) V.01",
    "Este documento es confidencial",
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _contains(haystack: str, needle: str) -> bool:
    return _normalize(needle) in _normalize(haystack)

OPTIONAL_REFERENCE = Path(
    "/Users/thewizard/Downloads/18.05.2026 HDM 4 HIDROSANITARIOS REV.2 3.pdf"
)


def extract_text(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        print("Instala pypdf en el venv del backend.", file=sys.stderr)
        sys.exit(2)
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        return [f"Archivo no encontrado: {path}"]
    text = extract_text(path)
    if not text.strip():
        errors.append("No se pudo extraer texto del PDF.")
    for needle in REQUIRED_STRINGS:
        if not _contains(text, needle):
            errors.append(f"Falta cadena requerida: {needle!r}")
    try:
        from pypdf import PdfReader

        pages = len(PdfReader(str(path)).pages)
        if pages < 1:
            errors.append(f"Se esperaba al menos 1 página, hay {pages}.")
        if "Plano anotado" in text and pages < 2:
            errors.append(f"PDF con planos anotados debería tener ≥2 páginas, hay {pages}.")
    except Exception as exc:
        errors.append(f"No se pudo leer páginas: {exc}")
    return errors


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Uso: {sys.argv[0]} <pdf_generado> [pdf_referencia]", file=sys.stderr)
        sys.exit(1)
    generated = Path(sys.argv[1])
    reference = Path(sys.argv[2]) if len(sys.argv) > 2 else OPTIONAL_REFERENCE

    print(f"Validando: {generated}")
    errors = validate(generated)
    if errors:
        print("FALLO:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    print("OK — estructura GA-FO-08 presente.")
    if reference.is_file():
        ref_text = extract_text(reference)
        ref_pages = len(extract_text(reference).split("---"))  # rough
        gen_pages = len(extract_text(generated).split("---"))
        print(f"Referencia: {reference.name} ({len(ref_text)} chars)")
        print(f"Generado:   {generated.name}")
        missing_in_gen = [s for s in REQUIRED_STRINGS if s in ref_text and s not in extract_text(generated)]
        if missing_in_gen:
            print("Advertencia — presentes en referencia pero no en generado:", missing_in_gen)
        del ref_pages, gen_pages
    sys.exit(0)


if __name__ == "__main__":
    main()
