from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


CoordinateSpace = Literal["world", "model"]
ViewerStatus = Literal["open", "reviewed", "ignored", "resolved"]


class BBox3D(BaseModel):
    min_x: float
    min_y: float
    min_z: float = 0.0
    max_x: float
    max_y: float
    max_z: float = 0.0


class Point3D(BaseModel):
    x: float
    y: float
    z: float = 0.0


class ViewerCoordinateSettings(BaseModel):
    coordinate_space: CoordinateSpace = "world"
    scale: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0
    invert_y: bool = False
    rotation_degrees: float = 0.0
    unit_factor: float = 1.0
    notes: str | None = None


class ViewerClash(BaseModel):
    id: str
    source_clash_id: str
    job_id: str | None = None
    project_id: str
    dwg_a: str | None = None
    dwg_b: str | None = None
    file_pair: list[str | None] = Field(default_factory=list)
    file_id_a: str | None = None
    file_id_b: str | None = None
    discipline_a: str
    discipline_b: str
    layer_a: str
    layer_b: str
    entity_a_id: str | None = None
    entity_b_id: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    viewer_dbid_a: int | None = None
    viewer_dbid_b: int | None = None
    clash_type: Literal["hard_2d", "hard_3d", "soft_clearance", "rule_based", "process_4d", "unknown"]
    confidence: Literal["low", "medium", "high"]
    severity: Literal["critical", "high", "medium", "low"]
    status: ViewerStatus = "open"
    raw_model_bbox_mm: BBox3D | None = None
    raw_world_bbox_mm: BBox3D | None = None
    model_bbox_mm: BBox3D
    world_bbox_mm: BBox3D
    viewer_bbox: BBox3D
    mapper_applied: bool = False
    alignment_offset_mm: Point3D | None = None
    coordinate_notes: str | None = None
    center: Point3D
    description: str
    recommendation: str


class ClashViewerSummary(BaseModel):
    total: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class ClashViewerResponse(BaseModel):
    project_id: str
    coordinate_space: CoordinateSpace = "world"
    units: str = "mm"
    source: str = "motor_dupla"
    coordinate_settings_applied: ViewerCoordinateSettings = Field(default_factory=ViewerCoordinateSettings)
    warnings: list[str] = Field(default_factory=list)
    summary: ClashViewerSummary
    clashes: list[ViewerClash] = Field(default_factory=list)


class ViewerFileConfig(BaseModel):
    file_id: str | None = None
    filename: str
    urn: str
    viewable_guid: str | None = None
    sheet_id: str | None = None
    discipline: str | None = None


class ViewerConfigResponse(BaseModel):
    project_id: str
    urn: str
    default_viewable_guid: str | None = None
    viewer_mode: Literal["2d", "3d"] = "2d"
    units: str = "mm"
    default_coordinate_space: CoordinateSpace = "world"
    clashes_url: str
    token_url: str = "/api/aps/token"
    manifest_url: str
    viewables: list[ViewerFileConfig] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ApsTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None


class ApsManifestResponse(BaseModel):
    status: str
    progress: str | None = None
    urn: str
    derivatives: list[dict[str, Any]] = Field(default_factory=list)
    viewable_guid: str | None = None


class ApsTranslateResponse(BaseModel):
    project_id: str
    file_id: str
    filename: str
    aps_bucket_key: str
    aps_object_key: str
    aps_object_id: str
    aps_urn: str
    aps_derivative_status: str
    aps_viewable_guid: str | None = None


class ApsFileManifestRefreshResponse(BaseModel):
    project_id: str
    file_id: str
    aps_urn: str
    aps_derivative_status: str
    aps_viewable_guid: str | None = None
    progress: str | None = None


class ClashStatusUpdate(BaseModel):
    status: ViewerStatus
    comment: str | None = None


class MappingWarning(BaseModel):
    code: str
    message: str


class ClashMappingCandidatesResponse(BaseModel):
    clash_id: str
    viewer_dbid_a: int | None = None
    viewer_dbid_b: int | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    strategy: Literal["not_implemented", "bbox_spatial", "source_ref", "cad_handle", "aps_properties"] = "not_implemented"
    warnings: list[MappingWarning] = Field(default_factory=list)
