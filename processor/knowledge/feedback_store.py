"""
Human correction persistence and analysis for continuous learning.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


@dataclass
class Correction:
    project_id: str
    takeoff_key: str
    original_bc3_code: str | None
    corrected_bc3_code: str
    original_quantity: float
    corrected_quantity: float
    original_unit: str
    corrected_unit: str
    correction_type: str
    corrector_notes: str
    timestamp: str


def _infer_item_type_from_takeoff_key(takeoff_key: str) -> str:
    normalized = (takeoff_key or "").lower()
    if ":" in normalized:
        suffix = normalized.split(":")[-1]
        if suffix:
            return suffix
    tokens = normalized.replace("-", "_").split("_")
    return tokens[-1] if tokens else "unknown"


class FeedbackStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        self._corrections = self._load()

    def _load(self) -> list[Correction]:
        corrections: list[Correction] = []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if not line.strip():
                continue
            payload = json.loads(line)
            corrections.append(Correction(**payload))
        return corrections

    @property
    def corrections(self) -> list[Correction]:
        return list(self._corrections)

    def add(self, correction: Correction) -> None:
        payload = asdict(correction)
        if not payload.get("timestamp"):
            payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._corrections.append(Correction(**payload))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def get_corrections_for_type(self, item_type: str) -> list[Correction]:
        needle = (item_type or "").lower().strip()
        if not needle:
            return self.corrections
        return [
            correction
            for correction in self._corrections
            if needle in _infer_item_type_from_takeoff_key(correction.takeoff_key)
            or needle in correction.corrector_notes.lower()
        ]

    def get_accuracy_stats(self) -> dict[str, Any]:
        total = len(self._corrections)
        if total == 0:
            return {"total_corrections": 0, "accuracy_by_type": {}, "by_correction_type": {}}

        by_item_type: dict[str, int] = {}
        by_correction_type: dict[str, int] = {}
        for correction in self._corrections:
            item_type = _infer_item_type_from_takeoff_key(correction.takeoff_key)
            by_item_type[item_type] = by_item_type.get(item_type, 0) + 1
            ctype = correction.correction_type
            by_correction_type[ctype] = by_correction_type.get(ctype, 0) + 1

        accuracy_by_type = {
            item_type: round(100.0 * (1.0 - (count / total)), 2)
            for item_type, count in by_item_type.items()
        }
        correction_rate_by_type = {
            item_type: round(100.0 * count / total, 2) for item_type, count in by_item_type.items()
        }

        return {
            "total_corrections": total,
            "accuracy_by_type": accuracy_by_type,
            "correction_rate_by_type": correction_rate_by_type,
            "by_correction_type": by_correction_type,
        }

    def export_for_fine_tuning(self) -> list[dict[str, Any]]:
        exported: list[dict[str, Any]] = []
        for correction in self._corrections:
            exported.append(
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": "Corrige partidas de presupuesto de construccion con criterios dominicanos.",
                        },
                        {
                            "role": "user",
                            "content": (
                                f"takeoff_key={correction.takeoff_key}\n"
                                f"bc3_original={correction.original_bc3_code}\n"
                                f"qty_original={correction.original_quantity} {correction.original_unit}\n"
                                f"notas={correction.corrector_notes}"
                            ),
                        },
                        {
                            "role": "assistant",
                            "content": (
                                f'{{"bc3_code":"{correction.corrected_bc3_code}",'
                                f'"quantity":{correction.corrected_quantity},'
                                f'"unit":"{correction.corrected_unit}"}}'
                            ),
                        },
                    ],
                    "metadata": {
                        "project_id": correction.project_id,
                        "correction_type": correction.correction_type,
                        "timestamp": correction.timestamp,
                    },
                }
            )
        return exported


def apply_corrections_to_rules(feedback_store: FeedbackStore, rules_engine: Any) -> list[dict[str, Any]]:
    grouped: dict[str, list[Correction]] = {}
    for correction in feedback_store.corrections:
        key = f"{_infer_item_type_from_takeoff_key(correction.takeoff_key)}::{correction.correction_type}"
        grouped.setdefault(key, []).append(correction)

    suggestions: list[dict[str, Any]] = []
    for key, bucket in grouped.items():
        if len(bucket) <= 3:
            continue
        item_type, correction_type = key.split("::", 1)
        suggestion = {
            "item_type": item_type,
            "correction_type": correction_type,
            "occurrences": len(bucket),
            "suggestion": (
                f"Se detectaron {len(bucket)} correcciones repetidas para '{item_type}' "
                f"({correction_type}). Revisar regla/factor en rules_engine manualmente."
            ),
            "sample_notes": [entry.corrector_notes for entry in bucket[:3]],
            "rule_engine_loaded": rules_engine is not None,
        }
        suggestions.append(suggestion)
    return suggestions
