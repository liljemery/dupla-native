from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

@dataclass
class MaterialsSheetConfig:
    sheet_names: tuple[str, ...] = ("lista", "precios")
    col_code: int = 0
    col_desc: int = 1
    col_unit: int = 2
    col_price: int = 4
    col_date: int = 6

@dataclass
class LaborSheetConfig:
    sheet_names: tuple[str, ...] = ("mo ", " mo", "mano")
    col_code: int = 0
    col_desc: int = 1
    col_qty: int = 7
    col_unit: int = 9
    col_price: int = 11
    col_price_fallback: int = 13

@dataclass
class ApusSheetConfig:
    sheet_names: tuple[str, ...] = ("analisis",)
    col_code: int = 0
    col_desc: int = 1
    col_qty: int = 2
    col_unit: int = 3
    col_price: int = 4
    col_subtotal: int = 5
    col_total: int = 6
    col_total_unit: int = 7

@dataclass
class PricingExcelConfig:
    materials: MaterialsSheetConfig = field(default_factory=MaterialsSheetConfig)
    labor: LaborSheetConfig = field(default_factory=LaborSheetConfig)
    apus: ApusSheetConfig = field(default_factory=ApusSheetConfig)


@dataclass
class MaterialPrice:
    code: str
    description: str
    unit: str
    unit_price: float
    category: str
    updated_date: str | None
    source: str
    currency: str = "USD"  # constructor xlsx is USD per the office


@dataclass
class LaborRate:
    code: str
    description: str
    unit: str
    unit_price: float
    category: str
    source: str
    currency: str = "USD"


@dataclass
class APUComponent:
    description: str
    quantity: float
    unit: str
    unit_price: float
    subtotal: float
    component_type: str  # "material" | "labor" | "equipment" | "overhead"


@dataclass
class APUBreakdown:
    code: str
    description: str
    unit: str
    unit_price_total: float
    category: str
    components: list[APUComponent]
    source: str
    currency: str = "USD"


@dataclass
class PricingStore:
    materials: dict[str, MaterialPrice] = field(default_factory=dict)
    labor: dict[str, LaborRate] = field(default_factory=dict)
    apus: dict[str, APUBreakdown] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "metadata": dict(self.metadata),
            "materials": {k: asdict(v) for k, v in self.materials.items()},
            "labor": {k: asdict(v) for k, v in self.labor.items()},
            "apus": {k: asdict(v) for k, v in self.apus.items()},
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PricingStore":
        materials = {
            k: MaterialPrice(**v) for k, v in (payload.get("materials") or {}).items()
        }
        labor = {
            k: LaborRate(**v) for k, v in (payload.get("labor") or {}).items()
        }
        apus: dict[str, APUBreakdown] = {}
        for k, v in (payload.get("apus") or {}).items():
            components = [APUComponent(**c) for c in v.get("components", [])]
            data = {**v, "components": components}
            apus[k] = APUBreakdown(**data)
        return cls(
            materials=materials,
            labor=labor,
            apus=apus,
            metadata=dict(payload.get("metadata") or {}),
        )
