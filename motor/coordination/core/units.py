"""Normalización de unidades para el motor 2.5D (coordenadas en mm)."""

from __future__ import annotations

from typing import Literal

Unit = Literal["mm", "cm", "m"]


def to_mm(value: float, unit: Unit) -> float:
    """Convierte una longitud al sistema interno del motor de coordinación (milímetros)."""
    if unit == "mm":
        return float(value)
    if unit == "cm":
        return float(value) * 10.0
    if unit == "m":
        return float(value) * 1000.0
    raise ValueError(f"Unidad no soportada: {unit!r}")


def from_mm(value_mm: float, unit: Unit) -> float:
    """Convierte desde mm al unit solicitado (para reportes)."""
    if unit == "mm":
        return float(value_mm)
    if unit == "cm":
        return float(value_mm) / 10.0
    if unit == "m":
        return float(value_mm) / 1000.0
    raise ValueError(f"Unidad no soportada: {unit!r}")
