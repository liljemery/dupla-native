from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.models.workspace import Workspace


@dataclass(frozen=True)
class WorkspaceContext:
    workspace_id: UUID
    workspace: Workspace

    @property
    def uuid(self) -> UUID:
        return self.workspace_id
