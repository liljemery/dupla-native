"""Modelos 2.5D: huella 2D + intervalo vertical con referencia de nivel y envolvente física."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from coordination.core.units import to_mm


class Discipline(str, Enum):
    ARCH = "ARQUITECTURA"
    STRUC = "ESTRUCTURA"
    MEP_PLUMBING = "FONTANERIA"
    MEP_HVAC = "CLIMATIZACION"
    MEP_ELEC = "ELECTRICIDAD"


class ElevationMode(str, Enum):
    RELATIVE_TO_LEVEL = "relative"
    PROJECT_ABSOLUTE = "absolute"


class AttachmentPoint(str, Enum):
    FLOOR = "floor_finish"
    SOFFIT = "structure_soffit"
    CEILING = "ceiling_finish"
    WALL_HIGH = "wall_high"
    FREE_STANDING = "free_standing"
    UNKNOWN = "unknown"


VerticalReferencePoint = Literal["bottom", "center", "top"]


class ProjectLevel(BaseModel):
    """Registro único de nivel: offset del cero del nivel respecto al Project Zero (mm)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    offset_to_project_zero_mm: float = 0.0
    discipline_origin: Discipline | None = None
    provisional: bool = False


class ZInterval(BaseModel):
    """Cota vertical: referencia + espesor/diámetro para envolvente, tolerancias y MEP."""

    model_config = ConfigDict(extra="forbid")

    level_id: str
    mode: ElevationMode = ElevationMode.RELATIVE_TO_LEVEL

    z_ref_raw_mm: float = Field(..., description="Cota de referencia (mm), según mode y reference_point")
    thickness_mm: float = Field(
        ...,
        ge=0.0,
        description="Altura del prisma o diámetro exterior (mm); 0 = lámina sin espesor modelado",
    )
    reference_point: VerticalReferencePoint = "bottom"

    attachment: AttachmentPoint = AttachmentPoint.UNKNOWN
    invert_level_hint: bool = Field(
        default=False,
        description="True si z_ref_raw_mm es intrados (invert); la envolvente sigue siendo reference_point+thickness",
    )

    measurement_uncertainty_mm: float = Field(default=20.0, ge=0.0)
    clearance_required_mm: float = Field(default=0.0, ge=0.0)

    def compute_envelope_relative_mm(self) -> tuple[float, float]:
        """Intervalo [z_min, z_max] en el mismo espacio que z_ref_raw_mm (relativo al nivel o absoluto)."""
        zr = self.z_ref_raw_mm
        t = self.thickness_mm
        if self.reference_point == "bottom":
            return (zr, zr + t)
        if self.reference_point == "center":
            half = t / 2.0
            return (zr - half, zr + half)
        return (zr - t, zr)


class Element25D(BaseModel):
    """Elemento listo para clash 2.5D (huella serializable + ZInterval)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source_ref: str
    discipline: Discipline
    category: str = "generic"
    footprint_coords_mm: list[tuple[float, float]] = Field(
        ...,
        description="Polígono cerrado en mm (plano); el motor cierra implícitamente si el LLM omitió el cierre",
    )
    z_data: ZInterval
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_absolute_interval_mm(
        self,
        level_offsets_mm: dict[str, float],
        *,
        strict_levels: bool = True,
    ) -> tuple[float, float]:
        """
        Intervalo en el eje Project Zero (mm), aplicando incertidumbre + holgura al envolvente.
        """
        z0_rel, z1_rel = self.z_data.compute_envelope_relative_mm()
        if z0_rel > z1_rel:
            raise ValueError(f"Envolvente invertida para elemento {self.id}")

        if self.z_data.mode == ElevationMode.PROJECT_ABSOLUTE:
            base = 0.0
        else:
            if self.z_data.level_id not in level_offsets_mm:
                msg = f"Nivel {self.z_data.level_id!r} no registrado (elemento {self.id})"
                if strict_levels:
                    raise ValueError(msg)
                base = 0.0
            else:
                base = level_offsets_mm[self.z_data.level_id]

        s = self.z_data.measurement_uncertainty_mm + self.z_data.clearance_required_mm
        return (base + z0_rel - s, base + z1_rel + s)


def element_from_inventory_meters(
    *,
    id: str,
    source_ref: str,
    discipline: Discipline,
    category: str,
    footprint_xy_m: list[tuple[float, float]],
    z_interval: ZInterval,
    metadata: dict[str, Any] | None = None,
) -> Element25D:
    """Puente desde inventario Dupla (m en planta) al motor 2.5D (mm)."""
    coords_mm = [(to_mm(x, "m"), to_mm(y, "m")) for x, y in footprint_xy_m]
    return Element25D(
        id=id,
        source_ref=source_ref,
        discipline=discipline,
        category=category,
        footprint_coords_mm=coords_mm,
        z_data=z_interval,
        metadata=dict(metadata or {}),
    )
