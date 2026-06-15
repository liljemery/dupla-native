from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class GroupKind(str, Enum):
    TIRADA = "tirada"
    PLANO = "plano"
    FASE = "fase"


class ArchitectureItem(BaseModel):
    id: UUID
    descripcion: str = Field(..., min_length=1)
    capitulo: Optional[str] = None
    partida: Optional[str] = None
    unidad: Optional[str] = None
    cantidad: Optional[float] = Field(default=None, ge=0)
    precio_unitario: Optional[float] = Field(default=None, ge=0)
    subtotal: Optional[float] = Field(default=None, ge=0)
    notas: Optional[str] = None


class ArchitectureGroup(BaseModel):
    id: UUID
    kind: GroupKind
    title: str = Field(..., min_length=1)
    order: int = Field(..., ge=0)
    items: list[ArchitectureItem] = Field(default_factory=list)


class MaterialRow(BaseModel):
    id: UUID
    categoria: Optional[str] = None
    descripcion: str = Field(..., min_length=1)
    unidad: Optional[str] = None
    cantidad_estimada: Optional[float] = Field(default=None, ge=0)
    desperdicio_porcentaje: Optional[float] = Field(default=None, ge=0, le=100)
    cantidad_total: Optional[float] = Field(default=None, ge=0)
    costo_estimado: Optional[float] = Field(default=None, ge=0)
    proveedor_sugerido: Optional[str] = None


class ArchitectureDocumentPayload(BaseModel):
    groups: list[ArchitectureGroup] = Field(default_factory=list)
    materiales: list[MaterialRow] = Field(default_factory=list)

    @field_validator("groups")
    @classmethod
    def sort_groups(cls, v: list[ArchitectureGroup]) -> list[ArchitectureGroup]:
        return sorted(v, key=lambda g: g.order)


class ArchitectureDataResponse(BaseModel):
    project_uuid: UUID
    document: ArchitectureDocumentPayload
    updated_at: Optional[str] = None
