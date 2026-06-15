"""
Day 1 training preparation helpers.

This module builds a small, reproducible preparation bundle from a PRES.xlsx
source:
- dataset summary
- balanced holdout sample for manual evaluation
- optional comparison against a generated workbook
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from compare_budget import analyze_budget_pair
from knowledge.training_data import TrainingPair, extract_level_templates, extract_training_pairs


@dataclass(frozen=True)
class Day1HoldoutExample:
    code: str
    item_type: str
    unit: str
    context: str
    description: str
    quantity: float
    price: float
    amount: float


def _pair_sort_key(pair: TrainingPair) -> tuple[str, str, str, str]:
    return (
        pair.input_item_type,
        pair.output_bc3_code,
        pair.output_description,
        pair.input_context,
    )


def _pair_to_example(pair: TrainingPair) -> Day1HoldoutExample:
    return Day1HoldoutExample(
        code=pair.output_bc3_code,
        item_type=pair.input_item_type,
        unit=pair.input_unit,
        context=pair.input_context,
        description=pair.output_description,
        quantity=pair.output_quantity,
        price=pair.output_price,
        amount=pair.output_quantity * pair.output_price,
    )


def select_holdout_pairs(pairs: list[TrainingPair], limit: int = 40) -> list[TrainingPair]:
    """Select a balanced evaluation sample from the training pairs.

    The selection is round-robin by inferred item type so the holdout set keeps
    a mix of categories instead of being dominated by the most common class.
    """
    if limit <= 0 or not pairs:
        return []

    grouped: dict[str, list[TrainingPair]] = defaultdict(list)
    for pair in sorted(pairs, key=_pair_sort_key):
        grouped[pair.input_item_type].append(pair)

    item_types = sorted(grouped)
    if not item_types:
        return []

    selected: list[TrainingPair] = []
    positions: dict[str, int] = {item_type: 0 for item_type in item_types}

    while len(selected) < limit:
        progressed = False
        for item_type in item_types:
            bucket = grouped[item_type]
            index = positions[item_type]
            if index >= len(bucket):
                continue
            selected.append(bucket[index])
            positions[item_type] = index + 1
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break

    return selected


def summarize_training_pairs(pairs: list[TrainingPair]) -> dict[str, Any]:
    item_type_counts = Counter(pair.input_item_type for pair in pairs)
    unit_counts = Counter(pair.input_unit for pair in pairs if pair.input_unit)
    discipline_counts = Counter(
        (pair.input_context.partition("|")[2].strip() or "General") for pair in pairs
    )
    context_counts = Counter(pair.input_context for pair in pairs)
    chapter_codes = Counter(
        pair.output_bc3_code[:2] if pair.output_bc3_code else ""
        for pair in pairs
        if pair.output_bc3_code
    )

    return {
        "total_pairs": len(pairs),
        "unique_item_types": len(item_type_counts),
        "unique_units": len(unit_counts),
        "unique_contexts": len(context_counts),
        "top_item_types": item_type_counts.most_common(10),
        "top_units": unit_counts.most_common(10),
        "top_disciplines": discipline_counts.most_common(10),
        "top_contexts": context_counts.most_common(10),
        "top_chapter_codes": chapter_codes.most_common(10),
    }


def _example_records(examples: list[TrainingPair]) -> list[Day1HoldoutExample]:
    return [_pair_to_example(example) for example in examples]


def _format_counter_rows(rows: list[tuple[str, int]]) -> list[str]:
    lines: list[str] = []
    for label, count in rows:
        lines.append(f"- {label}: {count}")
    return lines


def _json_safe(value: Any) -> Any:
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, dict):
        return {key: _json_safe(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def build_day1_artifacts(
    pres_path: str | Path,
    output_dir: str | Path,
    *,
    generated_path: str | Path | None = None,
    holdout_limit: int = 40,
) -> dict[str, Any]:
    """Build the Day 1 prep bundle and persist the artifacts to disk."""
    pres_path = Path(pres_path).resolve()
    output_dir = Path(output_dir).resolve()
    if not pres_path.exists():
        raise FileNotFoundError(f"PRES source not found: {pres_path}")

    pairs = extract_training_pairs(pres_path)
    templates = extract_level_templates(pres_path)
    holdout_pairs = select_holdout_pairs(pairs, holdout_limit)
    summary = summarize_training_pairs(pairs)
    holdout_examples = _example_records(holdout_pairs)
    holdout_records = [asdict(example) for example in holdout_examples]

    comparison: dict[str, Any] | None = None
    generated_file: Path | None = None
    if generated_path is not None:
        generated_file = Path(generated_path).resolve()
        if generated_file.exists():
            comparison = analyze_budget_pair(generated_file, pres_path)

    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "pres_path": str(pres_path),
        "generated_path": str(generated_file) if generated_file else None,
        "summary": summary,
        "holdout_limit": holdout_limit,
        "holdout_examples": holdout_records,
        "templates": [asdict(template) for template in templates],
        "comparison": _json_safe(comparison) if comparison is not None else None,
    }

    manifest_path = output_dir / "day1_training_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    holdout_path = output_dir / "day1_holdout_eval.jsonl"
    with holdout_path.open("w", encoding="utf-8") as handle:
        for example in holdout_records:
            handle.write(json.dumps(example, ensure_ascii=False) + "\n")

    report_lines = [
        "# Day 1 training prep report",
        "",
        f"- PRES source: `{pres_path}`",
        f"- Holdout limit: {holdout_limit}",
        f"- Training pairs extracted: {summary['total_pairs']}",
        f"- Unique item types: {summary['unique_item_types']}",
        f"- Unique units: {summary['unique_units']}",
        f"- Unique contexts: {summary['unique_contexts']}",
        f"- Level templates detected: {len(templates)}",
        "",
        "## Top item types",
        "",
        *(_format_counter_rows(summary["top_item_types"])),
        "",
        "## Top disciplines",
        "",
        *(_format_counter_rows(summary["top_disciplines"])),
        "",
        "## Holdout examples",
        "",
        "| code | item_type | unit | context | description |",
        "| --- | --- | --- | --- | --- |",
    ]
    for example in holdout_examples:
        report_lines.append(
            f"| {example.code} | {example.item_type} | {example.unit} | {example.context} | {example.description} |"
        )

    if comparison is not None:
        real_disciplines = sorted(comparison.get("real_disciplines") or [])
        generated_disciplines = sorted(comparison.get("generated_disciplines") or [])
        missing_disciplines = sorted(set(real_disciplines) - set(generated_disciplines))
        report_lines.extend(
            [
                "",
                "## Baseline comparison",
                "",
                f"- Generated workbook: `{generated_file}`",
                f"- Coverage: {comparison['coverage']:.2f}%",
                f"- Quantity accuracy: {comparison['qty_accuracy']:.2f}%",
                f"- Price accuracy: {comparison['price_accuracy']:.2f}%",
                f"- Matched codes: {len(comparison['matching_codes'])}",
                f"- Generated partidas: {len(comparison['generated_partidas'])}",
                f"- Real partidas: {len(comparison['real_partidas'])}",
                "",
                "### Semantic family overlap",
                "",
                f"- Generated families: {', '.join(generated_disciplines) or '—'}",
                f"- Real families: {', '.join(real_disciplines) or '—'}",
                f"- Missing families vs real: {', '.join(missing_disciplines) or '—'}",
            ]
        )
    else:
        report_lines.extend(
            [
                "",
                "## Baseline comparison",
                "",
                "_No generated workbook supplied, so only the dataset prep bundle was written._",
            ]
        )

    report_path = output_dir / "day1_training_report.md"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    manifest["manifest_path"] = str(manifest_path)
    manifest["holdout_path"] = str(holdout_path)
    manifest["report_path"] = str(report_path)
    return manifest
