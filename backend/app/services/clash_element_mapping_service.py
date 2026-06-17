from __future__ import annotations

from typing import Any
from uuid import UUID


class ClashElementMappingService:
    """Placeholder infrastructure for future APS dbId resolution.

    The current viewer draws by bbox. These methods intentionally return empty
    candidates until we build APS property and spatial indexes.
    """

    async def find_candidates_by_bbox(self, project_id: UUID, clash: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    async def find_candidates_by_source_ref(self, project_id: UUID, clash: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    async def find_candidates_by_cad_handle(self, project_id: UUID, clash: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    async def find_candidates_by_aps_properties(self, project_id: UUID, clash: dict[str, Any]) -> list[dict[str, Any]]:
        return []
