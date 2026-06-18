"""Canonical layer role mapper for clash filtering.

Maps CAD layer names to CanonicalRoles using keyword matching and provides
a configurable matrix of role pairs that are structurally relevant.
"""

from __future__ import annotations

from enum import Enum
from typing import FrozenSet


class CanonicalRole(str, Enum):
    WALL = "wall"
    COLUMN = "column"
    BEAM = "beam"
    SLAB = "slab"
    OPENING = "opening"
    STAIR = "stair"
    RAILING = "railing"
    FOUNDATION = "foundation"
    ANNOTATION = "annotation"
    AXIS = "axis"
    FURNITURE = "furniture"
    DETAIL = "detail"
    UNKNOWN = "unknown"


# Roles that are never constructively relevant — always suppressed regardless of matrix
SUPPRESS_ALWAYS: frozenset[CanonicalRole] = frozenset({
    CanonicalRole.ANNOTATION,
    CanonicalRole.AXIS,
    CanonicalRole.FURNITURE,
    CanonicalRole.DETAIL,
})

# Default matrix: each entry is a frozenset of one or two CanonicalRole values.
# frozenset({A, B}) covers A-vs-B and B-vs-A symmetrically.
# frozenset({A}) covers A-vs-A (same-role clashes, e.g. WALL vs WALL).
DEFAULT_ROLE_MATRIX: frozenset[FrozenSet[CanonicalRole]] = frozenset({
    frozenset({CanonicalRole.WALL}),                                          # wall vs wall
    frozenset({CanonicalRole.WALL, CanonicalRole.COLUMN}),
    frozenset({CanonicalRole.WALL, CanonicalRole.BEAM}),
    frozenset({CanonicalRole.WALL, CanonicalRole.SLAB}),
    frozenset({CanonicalRole.WALL, CanonicalRole.OPENING}),
    frozenset({CanonicalRole.WALL, CanonicalRole.FOUNDATION}),
    frozenset({CanonicalRole.COLUMN, CanonicalRole.OPENING}),
    frozenset({CanonicalRole.COLUMN, CanonicalRole.FOUNDATION}),
    frozenset({CanonicalRole.STAIR, CanonicalRole.BEAM}),
    frozenset({CanonicalRole.STAIR, CanonicalRole.SLAB}),
    frozenset({CanonicalRole.RAILING, CanonicalRole.BEAM}),
    frozenset({CanonicalRole.SLAB, CanonicalRole.BEAM}),
    frozenset({CanonicalRole.SLAB, CanonicalRole.COLUMN}),
    frozenset({CanonicalRole.FOUNDATION, CanonicalRole.SLAB}),
})

# Keyword rules — first match wins.
# Each tuple is (keywords, CanonicalRole).  Ordered from most-specific to least.
_LAYER_KEYWORDS: list[tuple[tuple[str, ...], CanonicalRole]] = [
    # Suppress groups first (more specific keyword sets)
    (
        ("eje", " eje", "_eje", "axis", "grid", "rejilla", "cuadricula", "grilla"),
        CanonicalRole.AXIS,
    ),
    (
        (
            "texto", "text", "anno", "dim", "label", "nota", "cota", "acotac",
            "simbolo", "titulo", "escala", "marco", "hatch", "trama", "relleno",
            "patron", "leader", "revision", "stamp", "sello",
        ),
        CanonicalRole.ANNOTATION,
    ),
    (
        ("mueble", "mobil", "furniture", "mob.", "mob_", "decorac", "equipo", "sanitario_fij"),
        CanonicalRole.FURNITURE,
    ),
    (
        ("detalle", "detail", "detalles", "det.", "ampliacion", "typical", "simbologia"),
        CanonicalRole.DETAIL,
    ),
    # Constructive groups
    (
        (
            "muro", "wall", "tabique", "particion", "mamposteria",
            "bloque", "concreto", "hormigon", "h.a.", " h.a", "ha_",
            "muros", "walls",
        ),
        CanonicalRole.WALL,
    ),
    (
        ("columna", "column", "col.", "pilar", "soporte", "pilote_sup", "columnas"),
        CanonicalRole.COLUMN,
    ),
    (
        ("viga", "beam", "joist", "correa", "vigueta", "vigas", "viguetas"),
        CanonicalRole.BEAM,
    ),
    (
        ("losa", "slab", "forjado", "cubierta_est", "techo_est", "losas", "entrepiso"),
        CanonicalRole.SLAB,
    ),
    (
        (
            "apertura", "hueco", "vano", "abertura", "opening",
            "puerta", "ventana", "door", "window", "huecos",
        ),
        CanonicalRole.OPENING,
    ),
    (
        ("escalera", "stair", "rampa", "escalon", "escaleras", "stairs"),
        CanonicalRole.STAIR,
    ),
    (
        ("baranda", "rail", "railing", "barandal", "guardarail", "pasamano"),
        CanonicalRole.RAILING,
    ),
    (
        ("cimiento", "fundac", "foundation", "zapata", "pilote", "cimientos"),
        CanonicalRole.FOUNDATION,
    ),
]


def layer_to_role(layer_name: str) -> CanonicalRole:
    """Map a CAD layer name string to a CanonicalRole using keyword matching.

    Returns CanonicalRole.UNKNOWN when no keyword matches — callers should
    treat UNKNOWN as "pass-through" to avoid false negatives.
    """
    normalized = layer_name.strip().lower()
    if not normalized:
        return CanonicalRole.UNKNOWN
    for keywords, role in _LAYER_KEYWORDS:
        if any(kw in normalized for kw in keywords):
            return role
    return CanonicalRole.UNKNOWN


def is_constructive_pair(
    role_a: CanonicalRole,
    role_b: CanonicalRole,
    matrix: FrozenSet[FrozenSet[CanonicalRole]] | None = None,
) -> bool:
    """Return True if the two roles form a constructively relevant clash pair.

    Rules:
    - SUPPRESS_ALWAYS roles are always rejected.
    - UNKNOWN roles always pass (avoid false negatives when layer is unclassified).
    - Otherwise the pair must be in the matrix.
    """
    if role_a in SUPPRESS_ALWAYS or role_b in SUPPRESS_ALWAYS:
        return False
    if role_a == CanonicalRole.UNKNOWN or role_b == CanonicalRole.UNKNOWN:
        return True
    active_matrix = matrix if matrix is not None else DEFAULT_ROLE_MATRIX
    return frozenset({role_a, role_b}) in active_matrix


def layer_pair_is_constructive(
    layer_a: str | None,
    layer_b: str | None,
    matrix: FrozenSet[FrozenSet[CanonicalRole]] | None = None,
) -> bool:
    """Convenience wrapper: map two layer names to roles and check the matrix."""
    return is_constructive_pair(
        layer_to_role(layer_a or ""),
        layer_to_role(layer_b or ""),
        matrix,
    )
