"""Coordinación 2.5D — paquete top-level.

Re-exporta los símbolos públicos principales para compatibilidad con
``from coordination import clash_pairs`` y similares.
"""

from coordination.core.clash import (
    ClashConflict,
    ClashIncident,
    clash_pairs,
    conflicts_to_conflict_notes,
    group_conflicts_into_incidents,
)
from coordination.core.models_25d import (
    AttachmentPoint,
    Discipline,
    Element25D,
    ElevationMode,
    ProjectLevel,
    ZInterval,
    element_from_inventory_meters,
)
from coordination.core.registry import (
    ProjectLevelRegistry,
    ProjectLevelRegistryDocument,
    SourceExcludePattern,
    ViewLevelPattern,
)
from coordination.core.units import from_mm, to_mm

__all__ = [
    "AttachmentPoint",
    "ClashConflict",
    "ClashIncident",
    "Discipline",
    "Element25D",
    "ElevationMode",
    "ProjectLevel",
    "ProjectLevelRegistry",
    "ProjectLevelRegistryDocument",
    "SourceExcludePattern",
    "ViewLevelPattern",
    "ZInterval",
    "clash_pairs",
    "conflicts_to_conflict_notes",
    "element_from_inventory_meters",
    "from_mm",
    "group_conflicts_into_incidents",
    "to_mm",
]
