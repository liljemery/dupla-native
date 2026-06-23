from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_clash_item import ProjectClashItem
from app.models.project_clash_job import ProjectClashJob
from app.models.project_file import ProjectFile
from app.schemas.clash_viewer import BBox3D, ClashViewerResponse, ClashViewerSummary, ViewerClash, ViewerCoordinateSettings
from app.services.clash_coordinate_mapper import CoordinateMapper
from app.services.clash_service import extract_clash_artifacts
from app.services.viewer_coordinate_settings_service import default_coordinate_settings, mapper_from_settings

SEVERITIES = {"critical", "high", "medium", "low"}
CONFIDENCES = {"high", "medium", "low"}
CLASH_TYPES = {"hard_2d", "hard_3d", "soft_clearance", "rule_based", "process_4d", "unknown"}
RESOLVED_STATUSES = {"resolved", "closed", "false_positive"}


def _safe_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _bbox_from_bounds(bounds: Any, z_bounds: Any = None) -> BBox3D | None:
    if not isinstance(bounds, (list, tuple)) or len(bounds) < 4:
        return None
    min_z = 0.0
    max_z = 0.0
    if isinstance(z_bounds, (list, tuple)) and len(z_bounds) >= 2:
        min_z = _as_float(z_bounds[0])
        max_z = _as_float(z_bounds[1])
    return BBox3D(
        min_x=_as_float(bounds[0]),
        min_y=_as_float(bounds[1]),
        min_z=min_z,
        max_x=_as_float(bounds[2]),
        max_y=_as_float(bounds[3]),
        max_z=max_z,
    )


def _bbox_from_item(item: ProjectClashItem) -> BBox3D | None:
    values = (item.bounds_minx_mm, item.bounds_miny_mm, item.bounds_maxx_mm, item.bounds_maxy_mm)
    if any(v is None for v in values):
        return None
    min_z = 0.0
    max_z = _as_float(item.overlap_depth_mm, 0.0)
    raw = item.raw_json or {}
    rep = raw.get("representative_conflict") if isinstance(raw.get("representative_conflict"), dict) else raw
    z_range = rep.get("z_overlap_range_project_mm") if isinstance(rep, dict) else None
    if isinstance(z_range, (list, tuple)) and len(z_range) >= 2:
        min_z = _as_float(z_range[0])
        max_z = _as_float(z_range[1])
    return BBox3D(
        min_x=float(item.bounds_minx_mm),
        min_y=float(item.bounds_miny_mm),
        min_z=min_z,
        max_x=float(item.bounds_maxx_mm),
        max_y=float(item.bounds_maxy_mm),
        max_z=max_z,
    )


def _offset_bbox(bbox: BBox3D, dx: float, dy: float) -> BBox3D:
    return BBox3D(
        min_x=bbox.min_x - dx,
        min_y=bbox.min_y - dy,
        min_z=bbox.min_z,
        max_x=bbox.max_x - dx,
        max_y=bbox.max_y - dy,
        max_z=bbox.max_z,
    )


def _center_of(bbox: BBox3D) -> dict[str, float]:
    return {
        "x": (bbox.min_x + bbox.max_x) / 2.0,
        "y": (bbox.min_y + bbox.max_y) / 2.0,
        "z": (bbox.min_z + bbox.max_z) / 2.0,
    }


def _bbox_to_dict(bbox: BBox3D) -> dict[str, float]:
    return bbox.model_dump()


def _map_bbox(bbox: BBox3D, mapper: CoordinateMapper) -> BBox3D:
    return BBox3D(**mapper.map_bbox(_bbox_to_dict(bbox)))


def normalize_severity(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in SEVERITIES:
        return text
    if text in {"p1", "critical"}:
        return "critical"
    if text in {"p2", "alta"}:
        return "high"
    return "medium"


def normalize_confidence(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in CONFIDENCES else "medium"


def normalize_clash_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in CLASH_TYPES:
        return text
    mapping = {
        "hard": "hard_2d",
        "2d": "hard_2d",
        "3d": "hard_3d",
        "clearance": "soft_clearance",
        "soft": "soft_clearance",
        "rule": "rule_based",
        "4d": "process_4d",
        "process": "process_4d",
    }
    return mapping.get(text, "unknown")


def normalize_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"reviewed", "needs_review", "correction_required", "correction_uploaded", "pending_reanalysis"}:
        return "reviewed"
    if text in {"ignored", "false_positive"}:
        return "ignored"
    if text in {"resolved", "closed"}:
        return "resolved"
    return "open"


def normalize_discipline(value: Any, fallback_text: str | None = None) -> str:
    text = str(value or fallback_text or "").strip().lower()
    if not text:
        return "unknown"
    aliases = {
        "arquitectura": "architecture",
        "arquitectonico": "architecture",
        "arquitectónico": "architecture",
        "arq": "architecture",
        "estructura": "structure",
        "est": "structure",
        "electricidad": "electrical",
        "eléctrica": "electrical",
        "electrica": "electrical",
        "elec": "electrical",
        "fontaneria": "plumbing",
        "fontanería": "plumbing",
        "hidrosanitario": "plumbing",
        "sanitario": "plumbing",
        "plomeria": "plumbing",
        "mecanico": "mechanical",
        "mecánico": "mechanical",
        "hvac": "mechanical",
    }
    for needle, normalized in aliases.items():
        if needle in text:
            return normalized
    return text.replace(" ", "_")


def _source_refs_from_raw(raw: dict[str, Any]) -> list[str]:
    refs = raw.get("source_refs")
    if isinstance(refs, list):
        return [str(x) for x in refs if x]
    rep = raw.get("representative_conflict")
    if isinstance(rep, dict) and isinstance(rep.get("source_refs"), list):
        return [str(x) for x in rep["source_refs"] if x]
    return []


def _layers_from_raw(raw: dict[str, Any]) -> tuple[str | None, str | None]:
    rep = raw.get("representative_conflict") if isinstance(raw.get("representative_conflict"), dict) else raw
    layers = rep.get("raw_layers") if isinstance(rep, dict) else None
    if isinstance(layers, list):
        a = str(layers[0]) if len(layers) > 0 and layers[0] else None
        b = str(layers[1]) if len(layers) > 1 and layers[1] else None
        return a, b
    refs = _source_refs_from_raw(raw)
    parsed = []
    for ref in refs[:2]:
        parsed.append(ref.split("|autodesk_raw:", 1)[1] if "|autodesk_raw:" in ref else ref)
    while len(parsed) < 2:
        parsed.append(None)
    return parsed[0], parsed[1]


def _description(discipline_a: str, discipline_b: str, layer_a: str, layer_b: str, clash_type: str) -> str:
    return (
        f"Posible clash {clash_type} entre {discipline_a} y {discipline_b}. "
        f"Layers: {layer_a} / {layer_b}."
    )


def _recommendation(clash_type: str) -> str:
    if clash_type in {"hard_2d", "hard_3d"}:
        return "Validar alineación, elevación y corregir ubicación si se confirma interferencia."
    if clash_type == "soft_clearance":
        return "Validar tolerancia reglamentaria y separación mínima entre disciplinas."
    return "Revisar la regla de coordinación y confirmar el criterio con el equipo técnico."


class ClashViewerAdapter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def latest_job(self, project_id: UUID) -> ProjectClashJob | None:
        result = await self._session.execute(
            select(ProjectClashJob)
            .where(ProjectClashJob.project_id == project_id)
            .order_by(ProjectClashJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def build_response(
        self,
        project_id: UUID,
        *,
        coordinate_space: str = "world",
        severity: str | None = None,
        discipline: str | None = None,
        include_resolved: bool = False,
    ) -> ClashViewerResponse:
        space = "model" if coordinate_space == "model" else "world"
        warnings: list[str] = []
        coordinate_settings = await self._coordinate_settings(project_id, space)
        mapper = mapper_from_settings(coordinate_settings)
        mapper_applied = not mapper.is_identity()
        if mapper_applied:
            warnings.append("CUSTOM_COORDINATE_MAPPER_APPLIED")
        job = await self.latest_job(project_id)
        clashes: list[ViewerClash] = []
        if job is not None:
            items = await self._items_for_job(job.id)
            if items:
                clashes = await self._from_items(project_id, job, items, space, warnings, mapper, mapper_applied, coordinate_settings)
            else:
                clashes = await self._from_job_artifacts(project_id, job, space, warnings, mapper, mapper_applied, coordinate_settings)

        filtered = []
        severity_filter = severity.lower() if severity else None
        discipline_filter = discipline.lower() if discipline else None
        for clash in clashes:
            if severity_filter and clash.severity != severity_filter:
                continue
            if discipline_filter and discipline_filter not in {clash.discipline_a, clash.discipline_b}:
                continue
            if not include_resolved and clash.status == "resolved":
                continue
            filtered.append(clash)

        return ClashViewerResponse(
            project_id=str(project_id),
            coordinate_space=space,
            coordinate_settings_applied=coordinate_settings,
            warnings=list(dict.fromkeys(warnings)),
            summary=self._summary(filtered),
            clashes=filtered,
        )

    async def _coordinate_settings(self, project_id: UUID, coordinate_space: str) -> ViewerCoordinateSettings:
        try:
            from app.services.viewer_coordinate_settings_service import ViewerCoordinateSettingsService

            settings = await ViewerCoordinateSettingsService(self._session).get(project_id, coordinate_space)
            return settings.model_copy(update={"coordinate_space": coordinate_space})
        except Exception:
            return default_coordinate_settings(coordinate_space)

    async def _items_for_job(self, job_id: UUID) -> list[ProjectClashItem]:
        result = await self._session.execute(
            select(ProjectClashItem)
            .where(ProjectClashItem.job_id == job_id)
            .order_by(ProjectClashItem.priority, ProjectClashItem.clash_code)
        )
        return list(result.scalars().all())

    async def _from_items(
        self,
        project_id: UUID,
        job: ProjectClashJob,
        items: list[ProjectClashItem],
        coordinate_space: str,
        warnings: list[str],
        mapper: CoordinateMapper | None = None,
        mapper_applied: bool = False,
        coordinate_settings: ViewerCoordinateSettings | None = None,
    ) -> list[ViewerClash]:
        file_lookup = await self._file_lookup(project_id)
        out: list[ViewerClash] = []
        for idx, item in enumerate(items, start=1):
            clash = self._from_item(
                project_id,
                job,
                item,
                idx,
                coordinate_space,
                file_lookup,
                warnings,
                mapper,
                mapper_applied,
                coordinate_settings,
            )
            if clash is not None:
                out.append(clash)
        return out

    def _from_item(
        self,
        project_id: UUID,
        job: ProjectClashJob,
        item: ProjectClashItem,
        index: int,
        coordinate_space: str,
        file_lookup: dict[str, ProjectFile],
        warnings: list[str],
        mapper: CoordinateMapper | None = None,
        mapper_applied: bool = False,
        coordinate_settings: ViewerCoordinateSettings | None = None,
    ) -> ViewerClash | None:
        mapper = mapper or CoordinateMapper()
        model_bbox = _bbox_from_item(item)
        if model_bbox is None:
            warnings.append(f"MISSING_BBOX:{item.clash_code}")
            return None
        raw = item.raw_json or {}
        world_bbox = self._world_bbox_from_raw(raw)
        if world_bbox is None:
            dx = _as_float(item.alignment_dx_mm, 0.0)
            dy = _as_float(item.alignment_dy_mm, 0.0)
            if item.alignment_dx_mm is None or item.alignment_dy_mm is None:
                warnings.append(f"MISSING_ALIGNMENT_OFFSET:{item.clash_code}")
            world_bbox = _offset_bbox(model_bbox, dx, dy)
        raw_viewer_bbox = world_bbox if coordinate_space == "world" else model_bbox
        viewer_bbox = _map_bbox(raw_viewer_bbox, mapper)
        layer_a_raw, layer_b_raw = _layers_from_raw(raw)
        layer_a = item.layer_a or layer_a_raw or "unknown"
        layer_b = item.layer_b or layer_b_raw or "unknown"
        discipline_a = normalize_discipline(item.discipline_a, item.dwg_a or layer_a)
        discipline_b = normalize_discipline(item.discipline_b, item.dwg_b or layer_b)
        clash_type = self._clash_type_from_item(item)
        file_a = self._resolve_file(item.dwg_a, file_lookup, warnings)
        file_b = self._resolve_file(item.dwg_b, file_lookup, warnings)
        center = _center_of(viewer_bbox)
        return ViewerClash(
            id=f"CL-{index:04d}",
            source_clash_id=str(item.clash_code or item.id),
            job_id=str(job.id),
            project_id=str(project_id),
            dwg_a=item.dwg_a,
            dwg_b=item.dwg_b,
            file_pair=[item.dwg_a, item.dwg_b],
            file_id_a=str(file_a.id) if file_a else None,
            file_id_b=str(file_b.id) if file_b else None,
            discipline_a=discipline_a,
            discipline_b=discipline_b,
            layer_a=layer_a,
            layer_b=layer_b,
            entity_a_id=self._raw_entity_id(raw, "a"),
            entity_b_id=self._raw_entity_id(raw, "b"),
            source_refs=_source_refs_from_raw(raw),
            clash_type=clash_type,
            confidence=normalize_confidence(item.report_confidence),
            severity=normalize_severity(item.severity or item.priority),
            status=normalize_status(item.status),
            raw_model_bbox_mm=model_bbox,
            raw_world_bbox_mm=world_bbox,
            model_bbox_mm=model_bbox,
            world_bbox_mm=world_bbox,
            viewer_bbox=viewer_bbox,
            mapper_applied=mapper_applied,
            alignment_offset_mm={
                "x": _as_float(item.alignment_dx_mm, 0.0),
                "y": _as_float(item.alignment_dy_mm, 0.0),
                "z": 0.0,
            },
            coordinate_notes=coordinate_settings.notes if coordinate_settings else None,
            center=center,
            description=item.observation or _description(discipline_a, discipline_b, layer_a, layer_b, clash_type),
            recommendation=item.recommended_action or _recommendation(clash_type),
        )

    async def _from_job_artifacts(
        self,
        project_id: UUID,
        job: ProjectClashJob,
        coordinate_space: str,
        warnings: list[str],
        mapper: CoordinateMapper | None = None,
        mapper_applied: bool = False,
        coordinate_settings: ViewerCoordinateSettings | None = None,
    ) -> list[ViewerClash]:
        artifacts = extract_clash_artifacts(job.result)
        primary = _safe_json(artifacts.get("primary_incidents"))
        if primary.get("incidents"):
            raw_items = primary.get("incidents") or []
        else:
            report = _safe_json(artifacts.get("clash_project_report")) or _safe_json(job.result)
            raw_items = report.get("conflicts") or []
        out: list[ViewerClash] = []
        file_lookup = await self._file_lookup(project_id)
        for idx, raw in enumerate(raw_items, start=1):
            if not isinstance(raw, dict):
                continue
            clash = self._from_raw(
                project_id,
                job,
                raw,
                idx,
                coordinate_space,
                file_lookup,
                warnings,
                mapper,
                mapper_applied,
                coordinate_settings,
            )
            if clash is not None:
                out.append(clash)
        return out

    def _from_raw(
        self,
        project_id: UUID,
        job: ProjectClashJob,
        raw: dict[str, Any],
        index: int,
        coordinate_space: str,
        file_lookup: dict[str, ProjectFile],
        warnings: list[str],
        mapper: CoordinateMapper | None = None,
        mapper_applied: bool = False,
        coordinate_settings: ViewerCoordinateSettings | None = None,
    ) -> ViewerClash | None:
        mapper = mapper or CoordinateMapper()
        rep = raw.get("representative_conflict") if isinstance(raw.get("representative_conflict"), dict) else raw
        bounds = raw.get("plan_bounds_mm") or rep.get("plan_intersection_bounds_mm")
        z_bounds = rep.get("z_overlap_range_project_mm")
        model_bbox = _bbox_from_bounds(bounds, z_bounds)
        if model_bbox is None:
            warnings.append(f"MISSING_BBOX:{raw.get('incident_id') or raw.get('element_id_a') or index}")
            return None
        dx, dy = self._alignment_from_raw(raw)
        if dx is None or dy is None:
            warnings.append(f"MISSING_ALIGNMENT_OFFSET:{raw.get('incident_id') or index}")
            world_bbox = model_bbox
        else:
            world_bbox = _offset_bbox(model_bbox, dx, dy)
        raw_viewer_bbox = world_bbox if coordinate_space == "world" else model_bbox
        viewer_bbox = _map_bbox(raw_viewer_bbox, mapper)
        disciplines = raw.get("disciplines") if isinstance(raw.get("disciplines"), list) else []
        discipline_a = normalize_discipline(rep.get("discipline_a") or (disciplines[0] if len(disciplines) > 0 else None))
        discipline_b = normalize_discipline(rep.get("discipline_b") or (disciplines[1] if len(disciplines) > 1 else None))
        layer_a, layer_b = _layers_from_raw(raw)
        pair = raw.get("file_pair") if isinstance(raw.get("file_pair"), list) else []
        dwg_a = Path(str(pair[0])).name if len(pair) > 0 else None
        dwg_b = Path(str(pair[1])).name if len(pair) > 1 else None
        file_a = self._resolve_file(dwg_a, file_lookup, warnings)
        file_b = self._resolve_file(dwg_b, file_lookup, warnings)
        clash_type = normalize_clash_type(rep.get("clash_type"))
        return ViewerClash(
            id=f"CL-{index:04d}",
            source_clash_id=str(raw.get("incident_id") or raw.get("element_id_a") or f"raw-{index}"),
            job_id=str(job.id),
            project_id=str(project_id),
            dwg_a=dwg_a,
            dwg_b=dwg_b,
            file_pair=[dwg_a, dwg_b],
            file_id_a=str(file_a.id) if file_a else None,
            file_id_b=str(file_b.id) if file_b else None,
            discipline_a=discipline_a,
            discipline_b=discipline_b,
            layer_a=layer_a or "unknown",
            layer_b=layer_b or "unknown",
            entity_a_id=str(raw.get("element_id_a")) if raw.get("element_id_a") else None,
            entity_b_id=str(raw.get("element_id_b")) if raw.get("element_id_b") else None,
            source_refs=_source_refs_from_raw(raw),
            clash_type=clash_type,
            confidence=normalize_confidence(raw.get("confidence") or rep.get("confidence")),
            severity=normalize_severity(raw.get("priority") or raw.get("severity")),
            status="open",
            raw_model_bbox_mm=model_bbox,
            raw_world_bbox_mm=world_bbox,
            model_bbox_mm=model_bbox,
            world_bbox_mm=world_bbox,
            viewer_bbox=viewer_bbox,
            mapper_applied=mapper_applied,
            alignment_offset_mm={"x": dx or 0.0, "y": dy or 0.0, "z": 0.0} if dx is not None and dy is not None else None,
            coordinate_notes=coordinate_settings.notes if coordinate_settings else None,
            center=_center_of(viewer_bbox),
            description=str(raw.get("description") or _description(discipline_a, discipline_b, layer_a or "unknown", layer_b or "unknown", clash_type)),
            recommendation=_recommendation(clash_type),
        )

    def _world_bbox_from_raw(self, raw: dict[str, Any]) -> BBox3D | None:
        location = raw.get("location") if isinstance(raw.get("location"), dict) else {}
        world_bounds = raw.get("world_bounds") or location.get("world_bounds")
        if isinstance(world_bounds, dict):
            if "min" in world_bounds and "max" in world_bounds:
                return BBox3D(
                    min_x=_as_float(world_bounds["min"].get("x")),
                    min_y=_as_float(world_bounds["min"].get("y")),
                    min_z=_as_float(world_bounds["min"].get("z"), 0.0),
                    max_x=_as_float(world_bounds["max"].get("x")),
                    max_y=_as_float(world_bounds["max"].get("y")),
                    max_z=_as_float(world_bounds["max"].get("z"), 0.0),
                )
            return _bbox_from_bounds([
                world_bounds.get("min_x"),
                world_bounds.get("min_y"),
                world_bounds.get("max_x"),
                world_bounds.get("max_y"),
            ])
        return None

    def _alignment_from_raw(self, raw: dict[str, Any]) -> tuple[float | None, float | None]:
        alignment = raw.get("alignment_offset_mm")
        if isinstance(alignment, (list, tuple)) and len(alignment) >= 2:
            return _as_float(alignment[0]), _as_float(alignment[1])
        rep = raw.get("representative_conflict")
        if isinstance(rep, dict):
            alignment = rep.get("alignment_offset_mm")
            if isinstance(alignment, (list, tuple)) and len(alignment) >= 2:
                return _as_float(alignment[0]), _as_float(alignment[1])
        return None, None

    def _clash_type_from_item(self, item: ProjectClashItem) -> str:
        raw = item.raw_json or {}
        rep = raw.get("representative_conflict") if isinstance(raw.get("representative_conflict"), dict) else raw
        return normalize_clash_type(rep.get("clash_type") if isinstance(rep, dict) else None)

    def _raw_entity_id(self, raw: dict[str, Any], side: str) -> str | None:
        direct = raw.get(f"element_id_{side}")
        if direct:
            return str(direct)
        rep = raw.get("representative_conflict")
        if isinstance(rep, dict) and rep.get(f"element_id_{side}"):
            return str(rep[f"element_id_{side}"])
        return None

    async def _file_lookup(self, project_id: UUID) -> dict[str, ProjectFile]:
        result = await self._session.execute(select(ProjectFile).where(ProjectFile.project_id == project_id))
        files = list(result.scalars().all())
        out: dict[str, ProjectFile] = {}
        for file in files:
            name = Path(file.original_name or "").name
            if name:
                out[name.lower()] = file
                out[Path(name).stem.lower()] = file
        return out

    def _resolve_file(
        self,
        filename: str | None,
        file_lookup: dict[str, ProjectFile],
        warnings: list[str],
    ) -> ProjectFile | None:
        if not filename:
            return None
        name = Path(filename).name.lower()
        file = file_lookup.get(name) or file_lookup.get(Path(name).stem.lower())
        if file is None:
            warnings.append(f"FILE_NOT_RESOLVED:{filename}")
        return file

    def _summary(self, clashes: list[ViewerClash]) -> ClashViewerSummary:
        counts = {key: 0 for key in SEVERITIES}
        for clash in clashes:
            counts[clash.severity] = counts.get(clash.severity, 0) + 1
        return ClashViewerSummary(total=len(clashes), **counts)


def aps_urn_for_object(bucket_key: str, object_key: str) -> str:
    raw = f"urn:adsk.objects:os.object:{bucket_key}/{object_key}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
