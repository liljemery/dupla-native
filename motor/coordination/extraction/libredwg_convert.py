"""Convert binary DWG to DXF via LibreDWG dwg2dxf (FOSS)."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from coordination.extraction.cad_cache import (
    cache_json_path,
    file_cache_key,
    load_cached_json,
    save_cached_json,
)

logger = logging.getLogger("dupla.coordination.libredwg")

_BINARY_DWG_HEADERS = (b"AC10", b"AC1")

_DXF_VARIANT_SUFFIXES = ("", ".minimal", ".r2000")


class DwgConvertError(RuntimeError):
    """Structured dwg2dxf failure for upload gate / extraction manifest."""

    def __init__(self, message: str, *, error_code: str, detail: str = "") -> None:
        super().__init__(message)
        self.error_code = error_code
        self.detail = detail


def is_binary_dwg(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(8)
    except OSError:
        return False
    return head.startswith(_BINARY_DWG_HEADERS)


@lru_cache(maxsize=1)
def libredwg_version() -> str:
    """LibreDWG version string for cache keys and manifests."""
    override = (os.getenv("LIBREDWG_VERSION") or "").strip()
    if override:
        return override
    exe = dwg2dxf_executable()
    if exe is None:
        return "unknown"
    for flag in ("-V", "--version"):
        try:
            proc = subprocess.run(
                [str(exe), flag],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
            text = (proc.stdout or proc.stderr or "").strip()
            if text:
                return text.splitlines()[0][:80]
        except Exception:
            continue
    return "unknown"


def dwg2dxf_executable() -> Path | None:
    override = (os.getenv("LIBREDWG_DWG2DXF") or os.getenv("DWG2DXF_PATH") or "").strip()
    if override:
        candidate = Path(override)
        if candidate.is_file():
            return candidate
    found = shutil.which("dwg2dxf")
    return Path(found) if found else None


def dwg2dxf_available() -> bool:
    return dwg2dxf_executable() is not None


def classify_dwg2dxf_error(stderr: str, *, returncode: int) -> str:
    """Map LibreDWG stderr to a stable error_code."""
    text = (stderr or "").lower()
    if "not overwritten" in text or "write error" in text:
        return "WRITE_ERROR"
    if "read error" in text or "failed to decode" in text or "0x940" in text:
        return "READ_ERROR"
    if "invalid group code" in text or "invalid dxf" in text:
        return "PARSE_ERROR"
    if returncode != 0:
        return "CONVERSION_FAILED"
    return "CONVERSION_FAILED"


def _dxf_output_path(out_dir: Path, cache_key: str, variant: str) -> Path:
    suffix = "" if variant == "full" else f".{variant}"
    return out_dir / f"{cache_key}{suffix}.dxf"


def invalidate_cached_dxf(
    dwg_path: Path,
    *,
    cache_root: Path | None = None,
    output_dir: Path | None = None,
) -> None:
    """Drop cached DXF paths after ezdxf rejects a LibreDWG conversion."""
    dwg_path = Path(dwg_path)
    cache_key = file_cache_key(dwg_path)
    if cache_root is not None:
        cached_json = cache_json_path(cache_root, key=cache_key, suffix="dxf_path")
        if cached_json.is_file():
            try:
                cached_json.unlink()
            except OSError:
                logger.warning("Could not remove DXF cache index %s", cached_json)
    out_dir = Path(output_dir) if output_dir else dwg_path.parent / ".dxf_cache"
    for suffix in _DXF_VARIANT_SUFFIXES:
        candidate = out_dir / f"{cache_key}{suffix}.dxf"
        if candidate.is_file():
            try:
                candidate.unlink()
            except OSError:
                logger.warning("Could not remove corrupt DXF cache %s", candidate)


def _run_dwg2dxf(
    dwg_path: Path,
    dxf_path: Path,
    *,
    timeout_seconds: int | None = None,
    minimal: bool = False,
    as_version: str | None = None,
) -> None:
    exe = dwg2dxf_executable()
    if exe is None:
        raise DwgConvertError(
            "LibreDWG dwg2dxf not found",
            error_code="TOOL_MISSING",
            detail="Install libredwg or upload DXF exported from your CAD tool.",
        )

    dxf_path.parent.mkdir(parents=True, exist_ok=True)
    timeout = timeout_seconds or int(os.getenv("LIBREDWG_TIMEOUT_SECONDS", "600"))
    cmd = [str(exe), "-y", "-o", str(dxf_path)]
    if minimal:
        cmd.append("-m")
    if as_version:
        cmd.extend(["--as", as_version])
    cmd.append(str(dwg_path))
    logger.info("LibreDWG: %s", " ".join(cmd))
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0 or not dxf_path.is_file():
        detail = (proc.stderr or proc.stdout or "")[-800:]
        error_code = classify_dwg2dxf_error(detail, returncode=proc.returncode)
        raise DwgConvertError(
            f"{error_code}: dwg2dxf failed for {dwg_path.name}: {detail}",
            error_code=error_code,
            detail=detail,
        )


def convert_dwg_to_dxf(
    dwg_path: Path,
    *,
    output_dir: Path | None = None,
    cache_root: Path | None = None,
    timeout_seconds: int | None = None,
    minimal: bool = False,
    as_version: str | None = None,
    variant: str = "full",
) -> Path:
    """Return path to DXF; uses cache when cache_root is set (full variant only)."""
    dwg_path = Path(dwg_path)
    if dwg_path.suffix.lower() == ".dxf":
        return dwg_path
    if not is_binary_dwg(dwg_path):
        raise ValueError(f"Not a binary DWG: {dwg_path}")

    cache_key = file_cache_key(dwg_path)
    if cache_root is not None and variant == "full" and not minimal and not as_version:
        cached = load_cached_json(cache_root, key=cache_key, suffix="dxf_path")
        if isinstance(cached, dict):
            cached_path = Path(str(cached.get("path") or ""))
            if cached_path.is_file():
                return cached_path

    out_dir = Path(output_dir) if output_dir else dwg_path.parent / ".dxf_cache"
    dxf_path = _dxf_output_path(out_dir, cache_key, variant)
    _run_dwg2dxf(
        dwg_path,
        dxf_path,
        timeout_seconds=timeout_seconds,
        minimal=minimal,
        as_version=as_version,
    )

    if cache_root is not None and variant == "full" and not minimal and not as_version:
        save_cached_json(
            cache_root,
            key=cache_key,
            suffix="dxf_path",
            payload={"path": str(dxf_path.resolve())},
        )
    return dxf_path


def convert_dwg_to_dxf_resilient(
    dwg_path: Path,
    *,
    output_dir: Path | None = None,
    cache_root: Path | None = None,
    timeout_seconds: int | None = None,
) -> tuple[Path, str]:
    """Convert DWG with full/minimal/r2000 fallbacks; probe each DXF with ezdxf."""
    from coordination.extraction.dxf_geometry import probe_dxf_readable

    dwg_path = Path(dwg_path)
    if dwg_path.suffix.lower() == ".dxf":
        return dwg_path, "native_dxf"
    if not is_binary_dwg(dwg_path):
        raise ValueError(f"Not a binary DWG: {dwg_path}")

    ver = libredwg_version()
    cache_key = file_cache_key(dwg_path)
    out_dir = Path(output_dir) if output_dir else dwg_path.parent / ".dxf_cache"
    out_dir.mkdir(parents=True, exist_ok=True)

    if cache_root is not None:
        cached = load_cached_json(cache_root, key=cache_key, suffix="dxf_path")
        if isinstance(cached, dict):
            cached_path = Path(str(cached.get("path") or ""))
            tag = str(cached.get("geometry_source") or f"libredwg_{ver}_full")
            if cached_path.is_file() and probe_dxf_readable(cached_path):
                return cached_path, tag

    attempts: list[tuple[str, dict[str, object]]] = [
        ("full", {"minimal": False, "as_version": None}),
        ("minimal", {"minimal": True, "as_version": None}),
        ("r2000", {"minimal": False, "as_version": "r2000"}),
    ]
    last_detail = ""
    for variant, opts in attempts:
        dxf_path = _dxf_output_path(out_dir, cache_key, variant)
        try:
            _run_dwg2dxf(
                dwg_path,
                dxf_path,
                timeout_seconds=timeout_seconds,
                minimal=bool(opts["minimal"]),
                as_version=opts["as_version"] if isinstance(opts["as_version"], str) else None,
            )
        except DwgConvertError as exc:
            last_detail = exc.detail or str(exc)
            if dxf_path.is_file():
                dxf_path.unlink(missing_ok=True)
            continue
        if probe_dxf_readable(dxf_path):
            tag = f"libredwg_{ver}_{variant}"
            if cache_root is not None:
                save_cached_json(
                    cache_root,
                    key=cache_key,
                    suffix="dxf_path",
                    payload={
                        "path": str(dxf_path.resolve()),
                        "geometry_source": tag,
                    },
                )
            logger.info("DWG %s converted via dwg2dxf variant=%s", dwg_path.name, variant)
            return dxf_path, tag
        logger.warning("DWG %s variant=%s DXF failed ezdxf probe", dwg_path.name, variant)
        if dxf_path.is_file():
            dxf_path.unlink(missing_ok=True)

    raise DwgConvertError(
        f"PARSE_ERROR: no readable DXF variant for {dwg_path.name}",
        error_code="PARSE_ERROR",
        detail=last_detail,
    )


def display_name_from_storage(filename: str) -> str:
    """Strip UUID prefix from backend storage keys for human-readable provenance."""
    name = Path(filename).name
    match = re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_(.+)$", name, re.I)
    return match.group(1) if match else name
