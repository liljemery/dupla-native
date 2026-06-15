"""
Structured output directory management for pipeline runs.

Creates the per-discipline output layout:
    output/{timestamp}_{slug}/
        pipeline_report.json
        run_summary.json
        dupla_debug.log
        arquitectura/
            presupuesto_arquitectura.xlsx
            missing_attributes_arq.txt
            vision_inventory.json
            budget_output.json
        consolidado/
            presupuesto_consolidado.xlsx
            unclassified_elements.txt
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower().strip())
    return slug.strip("_")[:40]


class RunOutputDir:
    """Manages the directory layout for a single pipeline run."""

    def __init__(self, base_dir: str | Path, project_name: str, timestamp: str | None = None):
        ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = _slugify(project_name)
        self.root = Path(base_dir) / f"{ts}_{slug}"
        self.root.mkdir(parents=True, exist_ok=True)
        self._project_name = project_name

    @property
    def pipeline_report(self) -> Path:
        return self.root / "pipeline_report.json"

    @property
    def run_summary(self) -> Path:
        return self.root / "run_summary.json"

    @property
    def debug_log(self) -> Path:
        return self.root / "dupla_debug.log"

    def discipline_dir(self, discipline_id: str) -> Path:
        d = self.root / discipline_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def discipline_excel(self, discipline_id: str) -> Path:
        return self.discipline_dir(discipline_id) / f"presupuesto_{discipline_id}.xlsx"

    def discipline_bc3(self, discipline_id: str) -> Path:
        return self.discipline_dir(discipline_id) / f"presupuesto_{discipline_id}.bc3"

    def discipline_budget_json(self, discipline_id: str) -> Path:
        return self.discipline_dir(discipline_id) / "budget_output.json"

    def discipline_quality_json(self, discipline_id: str) -> Path:
        return self.discipline_dir(discipline_id) / "quality_report.json"

    def discipline_input_gaps_md(self, discipline_id: str) -> Path:
        return self.discipline_dir(discipline_id) / "INPUT_GAPS.md"

    def discipline_vision_json(self, discipline_id: str) -> Path:
        return self.discipline_dir(discipline_id) / "vision_inventory.json"

    def discipline_missing_attrs(self, discipline_id: str) -> Path:
        return self.discipline_dir(discipline_id) / f"missing_attributes_{discipline_id}.txt"

    @property
    def consolidado_dir(self) -> Path:
        d = self.root / "consolidado"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def consolidated_excel(self) -> Path:
        return self.consolidado_dir / "presupuesto_consolidado.xlsx"

    @property
    def consolidated_bc3(self) -> Path:
        return self.consolidado_dir / "presupuesto_consolidado.bc3"

    @property
    def unclassified_elements(self) -> Path:
        return self.consolidado_dir / "unclassified_elements.txt"

    @property
    def quantification_summary(self) -> Path:
        return self.consolidado_dir / "resumen_cuantificacion.txt"
