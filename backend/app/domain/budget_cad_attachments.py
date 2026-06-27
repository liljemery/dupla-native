"""Resolve auxiliary DXF paths for budget jobs (companions + upload-gate cache)."""

from __future__ import annotations

import sys
from pathlib import Path

from app.models.project_file import ProjectFile

_MOTOR_CANDIDATES = (
    Path("/motor"),
    Path(__file__).resolve().parents[3] / "motor",
)

ReadableCache = dict[str, bool]


def _ensure_motor_path() -> bool:
    for candidate in _MOTOR_CANDIDATES:
        resolved = candidate.resolve()
        if resolved.is_dir():
            text = str(resolved)
            if text not in sys.path:
                sys.path.insert(0, text)
            return True
    return False


def ingest_snapshot(row: ProjectFile) -> dict:
    snap = row.file_ingest_snapshot
    return snap if isinstance(snap, dict) else {}


def refresh_cad_gate_snapshots(files: list[ProjectFile]) -> list[ProjectFile]:
    """Re-probe DWG conversion on disk (picks up LibreDWG installed after upload)."""
    from app.domain.cad_upload_gate import validate_cad_upload

    touched: list[ProjectFile] = []
    for pf in files:
        if not (pf.original_name or "").lower().endswith(".dwg"):
            continue
        path = Path(pf.storage_key)
        if not path.is_file():
            continue
        gate = validate_cad_upload(path)
        status = gate.get("cad_conversion_status")
        if status is None:
            continue
        snap = dict(ingest_snapshot(pf))
        snap["cad_conversion_status"] = status
        message = gate.get("message")
        if message:
            snap["cad_conversion_note"] = message
        error_code = gate.get("cad_conversion_error_code")
        if error_code:
            snap["cad_conversion_error_code"] = error_code
        companion = gate.get("cad_companion_dxf")
        if companion:
            snap["cad_companion_dxf"] = companion
        pf.file_ingest_snapshot = snap
        touched.append(pf)
    return touched


def _trust_gate_cache(path: Path) -> bool:
    """Gate cache DXFs were validated on upload; skip re-probing ezdxf."""
    return path.is_file() and ".dxf_cache" in path.parts and path.stat().st_size > 0


def _cached_readable(path: Path, cache: ReadableCache | None) -> bool:
    if _trust_gate_cache(path):
        return True
    key = str(path.resolve())
    if cache is not None and key in cache:
        return cache[key]
    if not _ensure_motor_path():
        ok = False
    else:
        from coordination.extraction.companion_dxf import is_readable_dxf

        ok = is_readable_dxf(path)
    if cache is not None:
        cache[key] = ok
    return ok


def auxiliary_dxf_candidates(
    dwg_path: Path,
    upload_root: Path,
    *,
    readable_cache: ReadableCache | None = None,
) -> list[Path]:
    """Companion or gate-cached DXF for a DWG on disk."""
    if not _ensure_motor_path():
        return []
    from coordination.extraction.companion_dxf import resolve_companion_dxf, resolve_gate_dxf_cache

    dwg_path = Path(dwg_path)
    roots = [dwg_path.parent, upload_root]
    seen: set[str] = set()
    out: list[Path] = []
    for candidate in (
        resolve_companion_dxf(dwg_path, search_roots=roots),
        resolve_gate_dxf_cache(dwg_path),
    ):
        if candidate is None:
            continue
        key = str(candidate.resolve())
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file() and _cached_readable(candidate, readable_cache):
            out.append(candidate)
    return out


def dwg_has_usable_dxf(
    dwg_path: Path,
    upload_root: Path,
    budget_files: list[ProjectFile],
    *,
    readable_cache: ReadableCache | None = None,
) -> bool:
    stem = Path(dwg_path.name).stem.lower()
    for pf in budget_files:
        name = (pf.original_name or "").lower()
        if name.endswith(".dxf") and Path(pf.original_name).stem.lower() == stem:
            return True
    return bool(auxiliary_dxf_candidates(dwg_path, upload_root, readable_cache=readable_cache))


def unusable_dwg_names(
    budget_files: list[ProjectFile],
    upload_root: Path,
    *,
    readable_cache: ReadableCache | None = None,
) -> list[str]:
    """DWGs that failed conversion and have no DXF fallback."""
    bad_statuses = {"conversion_failed", "requires_dxf", "requires_dxf_export"}
    names: list[str] = []
    for pf in budget_files:
        if not (pf.original_name or "").lower().endswith(".dwg"):
            continue
        snap = ingest_snapshot(pf)
        status = str(snap.get("cad_conversion_status") or "")
        error_code = str(snap.get("cad_conversion_error_code") or "")
        if status not in bad_statuses and error_code != "READ_ERROR":
            continue
        disk_path = Path(pf.storage_key)
        if not disk_path.is_file():
            continue
        if dwg_has_usable_dxf(disk_path, upload_root, budget_files, readable_cache=readable_cache):
            continue
        names.append(pf.original_name)
    return names


def budget_dxf_stems(budget_files: list[ProjectFile]) -> set[str]:
    stems: set[str] = set()
    for pf in budget_files:
        name = (pf.original_name or "").lower()
        if name.endswith(".dxf"):
            stems.add(Path(pf.original_name).stem.lower())
    return stems
