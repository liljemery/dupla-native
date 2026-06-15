"""
Multi-discipline project input validation and routing.

Validates that each declared discipline has the required files (PDF mandatory,
DWG optional) and dispatches to the appropriate engine.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("dupla.inputs")


@dataclass
class DisciplineInput:
    """Input files for a single discipline."""

    discipline_id: str
    pdf_path: Path
    dwg_path: Path | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.pdf_path.exists():
            errors.append(f"[{self.discipline_id}] PDF not found: {self.pdf_path}")
        if self.dwg_path and not self.dwg_path.exists():
            errors.append(f"[{self.discipline_id}] DWG not found: {self.dwg_path}")
        return errors

    @property
    def has_dwg(self) -> bool:
        return self.dwg_path is not None and self.dwg_path.exists()


@dataclass
class ProjectInputs:
    """Validated project-level inputs for the multi-discipline pipeline."""

    project_name: str
    bc3_path: Path | None = None
    disciplines: dict[str, DisciplineInput] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.disciplines:
            errors.append("No disciplines declared in project inputs.")
        for disc_input in self.disciplines.values():
            errors.extend(disc_input.validate())
        if self.bc3_path and not self.bc3_path.exists():
            errors.append(f"BC3 catalog not found: {self.bc3_path}")
        return errors

    @property
    def active_discipline_ids(self) -> list[str]:
        return sorted(self.disciplines.keys())


def load_project_inputs(config_path: str | Path) -> ProjectInputs:
    """Load a ``dupla_project.json`` configuration file.

    Expected schema::

        {
            "project_name": "Torre Giualca I",
            "bc3_path": "data/TGIU.bc3",
            "disciplines": {
                "arquitectura": {"pdf": "arquitectura/planos.pdf", "dwg": "arquitectura/planos.dwg"},
                "estructura": {"pdf": "estructura/planos.pdf"}
            }
        }

    Paths are resolved relative to the config file's parent directory.
    """
    config_path = Path(config_path).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Project config not found: {config_path}")

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    base_dir = config_path.parent

    project_name = raw.get("project_name", config_path.stem)
    bc3_raw = raw.get("bc3_path")
    bc3_path = (base_dir / bc3_raw).resolve() if bc3_raw else None

    disciplines: dict[str, DisciplineInput] = {}
    for disc_id, files in (raw.get("disciplines") or {}).items():
        pdf_raw = files.get("pdf")
        if not pdf_raw:
            logger.warning("Discipline '%s' has no PDF declared, skipping.", disc_id)
            continue
        dwg_raw = files.get("dwg")
        disciplines[disc_id] = DisciplineInput(
            discipline_id=disc_id,
            pdf_path=(base_dir / pdf_raw).resolve(),
            dwg_path=(base_dir / dwg_raw).resolve() if dwg_raw else None,
        )

    metadata = {k: v for k, v in raw.items() if k not in {"project_name", "bc3_path", "disciplines"}}

    return ProjectInputs(
        project_name=project_name,
        bc3_path=bc3_path,
        disciplines=disciplines,
        metadata=metadata,
    )


def build_single_discipline_inputs(
    *,
    project_name: str,
    discipline_id: str = "arquitectura",
    pdf_path: str | Path,
    dwg_path: str | Path | None = None,
    bc3_path: str | Path | None = None,
    **metadata: Any,
) -> ProjectInputs:
    """Convenience builder for the single-discipline (backward-compatible) case."""
    return ProjectInputs(
        project_name=project_name,
        bc3_path=Path(bc3_path) if bc3_path else None,
        disciplines={
            discipline_id: DisciplineInput(
                discipline_id=discipline_id,
                pdf_path=Path(pdf_path),
                dwg_path=Path(dwg_path) if dwg_path else None,
            )
        },
        metadata=metadata,
    )
