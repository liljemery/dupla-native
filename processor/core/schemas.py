"""
Shared typed models for the active APS/JSON inventory pipeline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Literal, Mapping

InventorySource = Literal["json", "vision", "hybrid"]
_ALLOWED_SOURCES = {"json", "vision", "hybrid"}
BudgetRowType = Literal["chapter", "line", "subtotal"]
_ALLOWED_BUDGET_ROW_TYPES = {"chapter", "line", "subtotal"}


def _validate_source(source: str) -> None:
    if source not in _ALLOWED_SOURCES:
        raise ValueError(
            f"Invalid source '{source}'. Expected one of: {', '.join(sorted(_ALLOWED_SOURCES))}."
        )


def _validate_budget_row_type(row_type: str) -> None:
    if row_type not in _ALLOWED_BUDGET_ROW_TYPES:
        raise ValueError(
            f"Invalid budget row type '{row_type}'. Expected one of: {', '.join(sorted(_ALLOWED_BUDGET_ROW_TYPES))}."
        )


@dataclass(kw_only=True)
class ModelBase:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(kw_only=True)
class ProjectContext(ModelBase):
    project_id: str | None = None
    project_name: str | None = None
    building_block: str | None = None
    level_id: str | None = None
    source_json_path: str | None = None
    plan_image_paths: list[str] = field(default_factory=list)
    bc3_path: str | None = None
    measurement_unit: str = "m"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class InventoryEntity(ModelBase):
    id: str
    level_id: str | None = None
    source: InventorySource = "hybrid"
    source_refs: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    conflict_notes: list[str] = field(default_factory=list)
    confidence: float | None = None
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_source(self.source)


@dataclass(kw_only=True)
class Wall(InventoryEntity):
    source_layers: list[str] = field(default_factory=list)
    length_m: float | None = None
    height_m: float | None = None
    thickness_m: float | None = None
    area_m2: float | None = None
    material_hint: str | None = None
    wall_system: str | None = None
    interior_exterior_hint: str | None = None
    finish_required: bool | None = None
    structural: bool | None = None
    openings_count: int = 0


@dataclass(kw_only=True)
class Opening(InventoryEntity):
    wall_id: str | None = None
    opening_type: str = "void"
    count: int = 1
    width_m: float | None = None
    height_m: float | None = None
    area_m2: float | None = None
    source_layers: list[str] = field(default_factory=list)
    related_door_id: str | None = None
    related_window_id: str | None = None


@dataclass(kw_only=True)
class Door(InventoryEntity):
    source_layers: list[str] = field(default_factory=list)
    count: int = 1
    width_m: float | None = None
    height_m: float | None = None
    type_hint: str | None = None
    material_hint: str | None = None
    exterior: bool | None = None
    wall_id: str | None = None


@dataclass(kw_only=True)
class Window(InventoryEntity):
    source_layers: list[str] = field(default_factory=list)
    count: int = 1
    width_m: float | None = None
    height_m: float | None = None
    type_hint: str | None = None
    glazing_hint: str | None = None
    wall_id: str | None = None


@dataclass(kw_only=True)
class WetArea(InventoryEntity):
    kind: str = "bathroom"
    count: int = 1
    estimated_area_m2: float | None = None
    fixture_ids: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class Kitchen(InventoryEntity):
    count: int = 1
    estimated_area_m2: float | None = None
    island_present: bool | None = None
    fixture_ids: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class Stair(InventoryEntity):
    count: int = 1
    flights: int | None = None
    riser_count: int | None = None
    tread_count: int | None = None
    width_m: float | None = None
    elevation_change_m: float | None = None


@dataclass(kw_only=True)
class Fixture(InventoryEntity):
    fixture_type: str = "other"
    count: int = 1
    unit: str = "unit"
    location_hint: str | None = None


@dataclass(kw_only=True)
class ReinforcementDetail:
    """Structured reinforcement data read from plan notation."""
    main_bars: str | None = None       # "4#6+2#5"
    stirrups: str | None = None        # "#3@0.15"
    steel_grade: str | None = None     # "grado_60"
    tie_bars: str | None = None        # "2#4" (bastones)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReinforcementDetail":
        return cls(
            main_bars=data.get("main_bars"),
            stirrups=data.get("stirrups"),
            steel_grade=data.get("steel_grade"),
            tie_bars=data.get("tie_bars"),
        )


@dataclass(kw_only=True)
class StructuralElement(InventoryEntity):
    element_type: str = "other"
    count: int = 1
    length_m: float | None = None
    area_m2: float | None = None
    volume_m3: float | None = None
    material_hint: str | None = None
    cross_section_shape: str | None = None
    section_diameter_m: float | None = None
    section_width_m: float | None = None
    section_height_m: float | None = None
    span_m: float | None = None
    orientation: str | None = None
    load_bearing: bool | None = None
    reinforcement_hint: str | None = None
    reinforcement: ReinforcementDetail | None = None
    concrete_grade_hint: str | None = None
    steel_grade_hint: str | None = None
    host_level: str | None = None
    adjacent_elements: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class LevelInventory(ModelBase):
    level_id: str
    level_name: str
    building_block: str | None = None
    source: InventorySource = "hybrid"
    source_image: str | None = None
    source_view: str | None = None
    cad_hints: dict[str, Any] = field(default_factory=dict)
    floor_area_m2: float | None = None
    ceiling_area_m2: float | None = None
    space_types: list[str] = field(default_factory=list)
    system_notes: list[str] = field(default_factory=list)
    structural_notes: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    conflict_notes: list[str] = field(default_factory=list)
    walls: list[Wall] = field(default_factory=list)
    openings: list[Opening] = field(default_factory=list)
    doors: list[Door] = field(default_factory=list)
    windows: list[Window] = field(default_factory=list)
    wet_areas: list[WetArea] = field(default_factory=list)
    kitchens: list[Kitchen] = field(default_factory=list)
    stairs: list[Stair] = field(default_factory=list)
    fixtures: list[Fixture] = field(default_factory=list)
    structural_elements: list[StructuralElement] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    confidence: float | None = None

    def __post_init__(self) -> None:
        _validate_source(self.source)


@dataclass(kw_only=True)
class QuantityTrace(ModelBase):
    source_entity_ids: list[str] = field(default_factory=list)
    source_entity_sources: list[InventorySource] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    conflict_notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for source in self.source_entity_sources:
            _validate_source(source)


@dataclass(kw_only=True)
class QuantityTakeoff(ModelBase):
    """Deterministic quantity result.

    Common ``inputs`` trace keys include ``quantity_source``, ``formwork_type``,
    ``price_estimated`` and ``estimate_basis``. Price keys may be populated by
    the budget composer/resolver metadata rather than by the original takeoff.
    """
    item_key: str
    item_type: str
    level_id: str | None = None
    unit: str = ""
    quantity: float = 0.0
    formula: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    trace: QuantityTrace = field(default_factory=QuantityTrace)
    confidence: float = 1.0
    requiere_revision: bool = False


@dataclass(kw_only=True)
class BudgetCandidate(ModelBase):
    takeoff_key: str
    bc3_code: str
    summary: str
    unit: str
    score: float
    rationale: str
    source: str = "keyword_match"
    bc3_origin: str | None = None


@dataclass(kw_only=True)
class BudgetChapter(ModelBase):
    chapter_id: str
    code: str
    title: str
    level: int = 1
    building_block: str | None = None
    parent_id: str | None = None
    path: list[str] = field(default_factory=list)
    child_ids: list[str] = field(default_factory=list)
    line_keys: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class BudgetLine(ModelBase):
    line_id: str
    takeoff_key: str
    chapter_id: str
    code: str
    nat: str = "Partida"
    unit: str = ""
    summary: str = ""
    quantity: float = 0.0
    unit_price: float | None = None
    amount_formula: str | None = None
    candidate_code: str | None = None
    candidate_score: float | None = None
    source_refs: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class BudgetRow(ModelBase):
    row_type: BudgetRowType
    code: str = ""
    nat: str = ""
    unit: str = ""
    summary: str = ""
    quantity: Any = None
    unit_price: Any = None
    amount: Any = None
    chapter_id: str | None = None
    parent_chapter_id: str | None = None
    building_block: str | None = None
    level: int = 0
    takeoff_key: str | None = None
    source_refs: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    excel_row: int | None = None

    def __post_init__(self) -> None:
        _validate_budget_row_type(self.row_type)


def project_context_from_dict(data: Mapping[str, Any]) -> ProjectContext:
    return ProjectContext(
        project_id=data.get("project_id"),
        project_name=data.get("project_name"),
        building_block=data.get("building_block"),
        level_id=data.get("level_id"),
        source_json_path=data.get("source_json_path"),
        plan_image_paths=list(data.get("plan_image_paths", [])),
        bc3_path=data.get("bc3_path"),
        measurement_unit=str(data.get("measurement_unit", "m")),
        metadata=dict(data.get("metadata", {})),
    )


def _list_of(
    model_cls: Any,
    values: list[Mapping[str, Any]],
    level_id: str,
    default_source: InventorySource,
) -> list[Any]:
    items: list[Any] = []
    field_names = {field_def.name for field_def in fields(model_cls)}
    for value in values:
        payload = {key: item for key, item in dict(value).items() if key in field_names}
        payload.setdefault("level_id", level_id)
        payload.setdefault("source", default_source)
        items.append(model_cls(**payload))
    return items


def level_inventory_from_dict(
    data: Mapping[str, Any],
    *,
    default_source: InventorySource = "hybrid",
) -> LevelInventory:
    level_id = str(data.get("level_id") or data.get("level_name") or "level")
    source = data.get("source", default_source)
    return LevelInventory(
        level_id=level_id,
        level_name=str(data.get("level_name") or level_id),
        building_block=data.get("building_block"),
        source=source,
        source_image=data.get("source_image"),
        source_view=data.get("source_view"),
        cad_hints=dict(data.get("cad_hints", {})),
        floor_area_m2=data.get("floor_area_m2"),
        ceiling_area_m2=data.get("ceiling_area_m2"),
        space_types=list(data.get("space_types", [])),
        system_notes=list(data.get("system_notes", [])),
        structural_notes=list(data.get("structural_notes", [])),
        source_refs=list(data.get("source_refs", [])),
        assumptions=list(data.get("assumptions", [])),
        inputs=dict(data.get("inputs", {})),
        conflict_notes=list(data.get("conflict_notes", [])),
        walls=_list_of(Wall, list(data.get("walls", [])), level_id, source),
        openings=_list_of(Opening, list(data.get("openings", [])), level_id, source),
        doors=_list_of(Door, list(data.get("doors", [])), level_id, source),
        windows=_list_of(Window, list(data.get("windows", [])), level_id, source),
        wet_areas=_list_of(WetArea, list(data.get("wet_areas", [])), level_id, source),
        kitchens=_list_of(Kitchen, list(data.get("kitchens", [])), level_id, source),
        stairs=_list_of(Stair, list(data.get("stairs", [])), level_id, source),
        fixtures=_list_of(Fixture, list(data.get("fixtures", [])), level_id, source),
        structural_elements=_list_of(
            StructuralElement,
            list(data.get("structural_elements", [])),
            level_id,
            source,
        ),
        notes=list(data.get("notes", [])),
        confidence=data.get("confidence"),
    )
