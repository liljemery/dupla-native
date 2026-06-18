#!/usr/bin/env python3
"""Auditor del flujo de identificación de clashes.

Uso:
    python scripts/audit_clash_workflow.py project_workflow.json

El JSON esperado debe incluir, como mínimo:
{
  "current_phase": "architecture_review",
  "files": [
    {"path": "planos/arq.dwg", "discipline": "arquitectura", "type": "DWG"},
    {"path": "planos/est.dwg", "discipline": "estructura", "type": "DWG"},
    {"path": "planos/mep.dwg", "discipline": "MEP", "type": "DWG"}
  ]
}
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


WORKFLOW_PHASES = [
    "bootstrapping",
    "awaiting_files",
    "files_ingested",
    "architecture_review",
    "specifications",
    "budgeting_pipeline",
    "management_approval",
    "budget_approved",
]

REQUIRED_DISCIPLINES = {
    "arquitectura": {"arquitectura", "architecture", "arq"},
    "estructura": {"estructura", "structural", "structure", "est"},
    "mep": {"mep", "electrica", "eléctrica", "sanitario", "mecanica", "mecánica", "plomeria"},
}

SUPPORTED_FILE_TYPES = {"dwg", "dxf", "pdf"}


class AuditFailure(Exception):
    """Error controlado para marcar auditoría no superada."""


def load_project_config(config_path: Path) -> dict[str, Any]:
    """Carga y valida que el archivo JSON base exista y sea un objeto."""
    if not config_path.is_file():
        raise AuditFailure(f"No existe el archivo de configuración: {config_path}")

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AuditFailure(f"JSON inválido en {config_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise AuditFailure("La configuración del proyecto debe ser un objeto JSON.")
    return data


def log_result(log_path: Path, message: str) -> None:
    """Agrega una línea timestamped al archivo de auditoría."""
    timestamp = datetime.now().isoformat(timespec="seconds")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {message}\n")


def normalize_text(value: Any) -> str:
    """Normaliza texto para comparar fases, disciplinas y extensiones."""
    return str(value or "").strip().lower()


def validate_workflow_phase(config: dict[str, Any], log_path: Path) -> str:
    """Comprueba que la fase actual exista y que clashes corran en architecture_review."""
    phase = normalize_text(config.get("current_phase") or config.get("phase") or config.get("estado"))
    log_result(log_path, f"Fase actual declarada: {phase or '(vacía)'}")

    if phase not in WORKFLOW_PHASES:
        raise AuditFailure(
            f"Fase inválida: {phase!r}. Fases permitidas: {', '.join(WORKFLOW_PHASES)}"
        )

    for item in WORKFLOW_PHASES:
        status = "actual" if item == phase else "revisada"
        log_result(log_path, f"Fase {item}: {status}")

    if phase != "architecture_review":
        raise AuditFailure(
            "La identificación de clashes debe ejecutarse en la fase "
            f"'architecture_review', pero el proyecto está en {phase!r}."
        )
    return phase


def validate_loaded_files(config: dict[str, Any], log_path: Path) -> list[dict[str, Any]]:
    """Verifica que existan archivos DWG/DXF/PDF para arquitectura, estructura y MEP."""
    files = config.get("files") or config.get("received_files") or config.get("archivos")
    if not isinstance(files, list) or not files:
        raise AuditFailure("No se cargaron archivos del proyecto.")

    valid_files: list[dict[str, Any]] = []
    found_disciplines: set[str] = set()

    for file_entry in files:
        if not isinstance(file_entry, dict):
            log_result(log_path, f"Archivo ignorado por formato inválido: {file_entry!r}")
            continue

        path = str(file_entry.get("path") or file_entry.get("filename") or file_entry.get("name") or "")
        suffix = normalize_text(file_entry.get("type") or Path(path).suffix.lstrip("."))
        discipline = normalize_text(file_entry.get("discipline") or file_entry.get("disciplina"))

        if suffix not in SUPPORTED_FILE_TYPES:
            log_result(log_path, f"Archivo ignorado por tipo no soportado: {path} ({suffix})")
            continue

        valid_files.append(file_entry)
        for canonical, aliases in REQUIRED_DISCIPLINES.items():
            if discipline in aliases:
                found_disciplines.add(canonical)

        log_result(log_path, f"Archivo válido: path={path}, tipo={suffix}, disciplina={discipline}")

    missing = sorted(set(REQUIRED_DISCIPLINES) - found_disciplines)
    if missing:
        raise AuditFailure(
            "Faltan archivos para disciplina(s) requerida(s): "
            f"{', '.join(missing)}. Se encontraron: {', '.join(sorted(found_disciplines)) or 'ninguna'}."
        )

    log_result(log_path, "Validación de archivos superada: arquitectura, estructura y MEP presentes.")
    return valid_files


def audit_clash_detection(files: list[dict[str, Any]], log_path: Path) -> list[dict[str, Any]]:
    """Importa clash_detector e invoca identificar_clashes con los archivos validados."""
    try:
        clash_detector = importlib.import_module("clash_detector")
    except ImportError as exc:
        raise AuditFailure("No se pudo importar el módulo 'clash_detector'.") from exc

    identificar_clashes = getattr(clash_detector, "identificar_clashes", None)
    if not callable(identificar_clashes):
        raise AuditFailure("El módulo 'clash_detector' no expone una función callable 'identificar_clashes'.")

    log_result(log_path, f"Ejecutando clash_detector.identificar_clashes con {len(files)} archivo(s).")
    result = identificar_clashes(files)

    if not isinstance(result, list):
        raise AuditFailure(
            "identificar_clashes debe devolver una lista de colisiones; "
            f"devolvió {type(result).__name__}."
        )
    if not result:
        raise AuditFailure("identificar_clashes no devolvió colisiones; se esperaba al menos una.")

    for index, clash in enumerate(result, start=1):
        if not isinstance(clash, dict):
            raise AuditFailure(f"Colisión #{index} inválida: debe ser objeto/dict.")
        classification = normalize_text(
            clash.get("classification") or clash.get("clasificacion") or clash.get("type")
        )
        if classification not in {"hard", "soft", "proceso", "process"}:
            raise AuditFailure(
                f"Colisión #{index} sin clasificación válida "
                f"(hard, soft, proceso): {classification!r}."
            )
        log_result(log_path, f"Clash #{index}: clasificación={classification}, datos={json.dumps(clash, ensure_ascii=False)}")

    log_result(log_path, f"Detección de clashes superada: {len(result)} colisión(es).")
    return result


def run_audit(config_path: Path, log_path: Path) -> int:
    """Ejecuta la auditoría completa y devuelve código de salida."""
    log_result(log_path, "=" * 80)
    log_result(log_path, f"Iniciando auditoría para configuración: {config_path}")

    try:
        config = load_project_config(config_path)
        validate_workflow_phase(config, log_path)
        files = validate_loaded_files(config, log_path)
        clashes = audit_clash_detection(files, log_path)
    except AuditFailure as exc:
        message = f"AUDITORÍA NO SUPERADA: {exc}"
        log_result(log_path, message)
        print(f"ERROR: {message}", file=sys.stderr)
        return 1

    message = f"AUDITORÍA SUPERADA: identificación de clashes ejecutada correctamente ({len(clashes)} resultado(s))."
    log_result(log_path, message)
    print(message)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audita el flujo de identificación de clashes.")
    parser.add_argument(
        "config",
        nargs="?",
        default="project_workflow.json",
        help="Ruta del JSON de configuración del proyecto.",
    )
    parser.add_argument(
        "--log",
        default="audit_log.txt",
        help="Ruta del archivo de auditoría.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_audit(Path(args.config), Path(args.log))


if __name__ == "__main__":
    raise SystemExit(main())
