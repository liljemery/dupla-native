"""Probe DWG→DXF conversion for budget/classification metadata (non-blocking)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_MOTOR_CANDIDATES = (
    Path("/motor"),
    Path(__file__).resolve().parents[3] / "motor",
)

_MAX_NOTE_LEN = 400


def _ensure_motor_path() -> bool:
    for candidate in _MOTOR_CANDIDATES:
        resolved = candidate.resolve()
        if resolved.is_dir():
            text = str(resolved)
            if text not in sys.path:
                sys.path.insert(0, text)
            return True
    return False


def _short_error(exc: BaseException) -> str:
    text = str(exc).strip().replace("\n", " ")
    if len(text) > _MAX_NOTE_LEN:
        return text[: _MAX_NOTE_LEN - 3] + "..."
    return text


def _gate_result(
    *,
    status: str,
    message: str = "",
    error_code: str = "",
    companion_dxf: str = "",
) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": True, "cad_conversion_status": status}
    if message:
        out["message"] = message
    if error_code:
        out["cad_conversion_error_code"] = error_code
    if companion_dxf:
        out["cad_companion_dxf"] = companion_dxf
    return out


def validate_cad_upload(path: Path) -> dict[str, Any]:
    """Return conversion probe metadata. Always ok=True — originals are never rejected."""
    suffix = path.suffix.lower()
    if suffix == ".dxf":
        return _gate_result(status="native_dxf")
    if suffix != ".dwg":
        return {"ok": True, "cad_conversion_status": None}

    if not _ensure_motor_path():
        return _gate_result(
            status="probe_skipped",
            message="DWG guardado. La conversión FOSS no está disponible en este servidor.",
        )

    from coordination.extraction.companion_dxf import resolve_companion_dxf
    from coordination.extraction.libredwg_convert import (
        DwgConvertError,
        convert_dwg_to_dxf_resilient,
        dwg2dxf_available,
        is_binary_dwg,
    )

    companion = resolve_companion_dxf(path, search_roots=[path.parent])
    if companion is not None:
        return _gate_result(
            status="companion_dxf_available",
            message="DWG guardado. DXF companion detectado para presupuesto/clasificación.",
            companion_dxf=companion.name,
        )

    if not is_binary_dwg(path):
        return _gate_result(status="dwg_text_or_legacy")
    if not dwg2dxf_available():
        return _gate_result(
            status="requires_dxf",
            error_code="TOOL_MISSING",
            message=(
                "DWG guardado. LibreDWG no está instalado; presupuesto/clasificación "
                "pueden requerir un DXF exportado desde tu CAD."
            ),
        )
    try:
        convert_dwg_to_dxf_resilient(path, output_dir=path.parent / ".dxf_cache")
    except DwgConvertError as exc:
        companion = resolve_companion_dxf(path, search_roots=[path.parent])
        if companion is not None:
            return _gate_result(
                status="companion_dxf_available",
                message="DWG guardado. DXF companion detectado para presupuesto/clasificación.",
                companion_dxf=companion.name,
                error_code=exc.error_code,
            )
        if exc.error_code == "READ_ERROR":
            return _gate_result(
                status="requires_dxf_export",
                error_code=exc.error_code,
                message=(
                    "DWG AutoCAD 2018+ no decodificable con LibreDWG. "
                    "Exporta DXF desde CAD y súbelo junto al DWG."
                ),
            )
        return _gate_result(
            status="conversion_failed",
            error_code=exc.error_code,
            message=(
                "DWG guardado sin modificar. No se pudo generar DXF auxiliar para "
                f"presupuesto/clasificación: {_short_error(exc)}"
            ),
        )
    except Exception as exc:
        companion = resolve_companion_dxf(path, search_roots=[path.parent])
        if companion is not None:
            return _gate_result(
                status="companion_dxf_available",
                message="DWG guardado. DXF companion detectado para presupuesto/clasificación.",
                companion_dxf=companion.name,
            )
        return _gate_result(
            status="conversion_deferred",
            error_code="EXTRACTION_ERROR",
            message=(
                "DWG guardado sin modificar. No se pudo generar DXF auxiliar para "
                f"presupuesto/clasificación: {_short_error(exc)}"
            ),
        )
    return _gate_result(status="converted_to_dxf")
