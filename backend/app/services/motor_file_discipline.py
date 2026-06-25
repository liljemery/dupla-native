"""Run motor discipline inference (in-process or subprocess) and map to FileDiscipline."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from app.config import Settings, get_settings
from app.domain.file_discipline import FileDiscipline, parse_discipline
from app.services.folder_path_parts import folder_path_parts
from app.services.motor_discipline_types import MotorDisciplineInference

logger = logging.getLogger(__name__)


def _motor_root_candidates() -> list[Path]:
    out: list[Path] = []
    raw = (os.getenv("DUPLA_ROOT") or "").strip()
    if raw:
        out.append(Path(raw))
    out.append(Path(__file__).resolve().parents[3] / "motor")
    out.append(Path("/motor"))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in out:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _motor_root() -> Path | None:
    script_name = Path("coordination") / "scripts" / "infer_file_discipline.py"
    for root in _motor_root_candidates():
        if (root / script_name).is_file():
            return root
    return _motor_root_candidates()[0] if _motor_root_candidates() else None


def _ensure_motor_on_path(root: Path) -> None:
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


def _coordination_cache_root(settings: Settings) -> Path | None:
    del settings
    raw = (os.getenv("COORDINATION_CACHE_ROOT") or "").strip()
    return Path(raw) if raw else None


def _map_bucket_to_file_discipline(bucket: str | None) -> FileDiscipline | None:
    if not bucket:
        return None
    return parse_discipline(bucket)


def _payload_to_inference(payload: dict[str, Any]) -> MotorDisciplineInference:
    bucket = payload.get("discipline")
    disc = _map_bucket_to_file_discipline(bucket if isinstance(bucket, str) else None)
    snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
    return MotorDisciplineInference(
        discipline=disc,
        method=str(payload.get("method") or "inconclusive"),
        confidence=float(payload.get("confidence") or 0.0),
        snapshot=snapshot,
    )


def _run_infer_inprocess(
    *,
    storage_path: Path,
    rel_posix: str | None,
    settings: Settings,
    motor_root: Path,
) -> dict[str, Any]:
    del settings
    _ensure_motor_on_path(motor_root)
    from coordination.scripts.infer_file_discipline import build_payload

    cache_root = _coordination_cache_root(get_settings())
    return build_payload(
        storage_path,
        rel_posix=rel_posix,
        cache_root=cache_root,
    )


def _run_infer_subprocess(
    *,
    storage_path: Path,
    rel_posix: str | None,
    settings: Settings,
    motor_root: Path,
) -> dict[str, Any]:
    del settings
    script = motor_root / "coordination" / "scripts" / "infer_file_discipline.py"
    if not script.is_file():
        raise FileNotFoundError(f"motor infer script not found: {script}")

    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.pathsep.join(
        part for part in (str(motor_root), env.get("PYTHONPATH", "")) if part
    )

    cmd = [sys.executable, str(script), "--path", str(storage_path)]
    if rel_posix:
        cmd.extend(["--rel-posix", rel_posix])
    cache_root = _coordination_cache_root(get_settings())
    if cache_root is not None:
        cmd.extend(["--cache-root", str(cache_root)])

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=300,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(err or f"infer_file_discipline exited {proc.returncode}")
    line = (proc.stdout or "").strip().splitlines()[-1]
    payload = json.loads(line)
    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))
    return payload


def _run_infer(
    *,
    storage_path: Path,
    rel_posix: str | None,
    settings: Settings,
    object_key: str | None,
    original_name: str | None = None,
) -> MotorDisciplineInference:
    del object_key
    display_name = original_name or storage_path.name
    motor_root = _motor_root()
    if motor_root is not None and (motor_root / "coordination" / "scripts" / "infer_file_discipline.py").is_file():
        try:
            payload = _run_infer_inprocess(
                storage_path=storage_path,
                rel_posix=rel_posix,
                settings=settings,
                motor_root=motor_root,
            )
            return _payload_to_inference(payload)
        except Exception as exc:
            logger.warning("in-process motor inference failed, trying subprocess: %s", exc)
            try:
                payload = _run_infer_subprocess(
                    storage_path=storage_path,
                    rel_posix=rel_posix,
                    settings=settings,
                    motor_root=motor_root,
                )
                return _payload_to_inference(payload)
            except Exception as sub_exc:
                logger.warning("subprocess motor inference failed: %s", sub_exc)
                raise sub_exc from exc

    from app.services.fallback_file_discipline import infer_discipline_fallback

    logger.warning("motor unavailable; using backend fallback for %s", display_name)
    return infer_discipline_fallback(
        storage_path,
        original_name=display_name,
        rel_posix=rel_posix,
    )


async def infer_file_discipline_from_content(
    *,
    storage_path: Path,
    rel_posix: str | None,
    settings: Settings | None = None,
    object_key: str | None = None,
    original_name: str | None = None,
) -> MotorDisciplineInference:
    cfg = settings or get_settings()
    return await asyncio.to_thread(
        _run_infer,
        storage_path=storage_path,
        rel_posix=rel_posix,
        settings=cfg,
        object_key=object_key,
        original_name=original_name,
    )


async def folder_rel_posix_for_file(session, project_id: UUID, folder_id: UUID | None) -> str | None:
    parts = await folder_path_parts(session, project_id, folder_id)
    if not parts:
        return None
    return "/".join(parts)
