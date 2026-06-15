"""Day 2 dataset preparation helpers.

Day 2 turns extracted PRES training pairs into a supervised dataset bundle with
deterministic train/validation splits, methodology context, and JSONL exports
ready for downstream model work.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from knowledge.methodology_generator import generate_methodology_context
from knowledge.training_data import TrainingPair, extract_training_pairs


@dataclass(frozen=True)
class Day2DatasetRecord:
    record_id: str
    split: str
    input_item_type: str
    input_unit: str
    input_context: str
    prompt: str
    target_code: str
    target_description: str
    target_unit: str
    target_quantity: float
    target_price: float
    target_amount: float


def _pair_sort_key(pair: TrainingPair) -> tuple[str, str, str, str]:
    return (
        pair.input_item_type,
        pair.output_bc3_code,
        pair.output_description,
        pair.input_context,
    )


def _pair_key(pair: TrainingPair) -> tuple[str, str, str, str, str, str]:
    return (
        pair.input_item_type,
        pair.input_unit,
        pair.input_context,
        pair.output_bc3_code,
        pair.output_description,
        pair.source,
    )


def _format_counter_rows(rows: list[tuple[str, int]]) -> list[str]:
    return [f"- {label}: {count}" for label, count in rows]


def _md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|")


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


def _resolve_pres_paths(pres_path: str | Path | list[str | Path]) -> list[Path]:
    values: list[str | Path]
    if isinstance(pres_path, list):
        values = pres_path
    else:
        values = [pres_path]

    resolved: list[Path] = []
    seen: set[str] = set()
    for value in values:
        path = Path(value).resolve()
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        resolved.append(path)
    return resolved


def _is_likely_valid_code(code: str) -> bool:
    value = (code or "").strip()
    if not value or " " in value:
        return False
    return len(value) <= 32


def _is_likely_valid_unit(unit: str) -> bool:
    value = (unit or "").strip()
    if not value:
        return False
    if len(value) > 16:
        return False
    if value.count(" ") > 1:
        return False
    return True


def _source_quality_score(pairs: list[TrainingPair]) -> float:
    if not pairs:
        return 0.0
    valid = 0
    for pair in pairs:
        code_ok = _is_likely_valid_code(pair.output_bc3_code)
        unit_ok = _is_likely_valid_unit(pair.output_unit)
        desc_ok = bool((pair.output_description or "").strip())
        if code_ok and unit_ok and desc_ok:
            valid += 1
    return valid / len(pairs)


def select_validation_pairs(pairs: list[TrainingPair], limit: int = 40) -> list[TrainingPair]:
    """Select a balanced validation sample from the extracted pairs."""
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

    return {
        "total_pairs": len(pairs),
        "unique_item_types": len(item_type_counts),
        "unique_units": len(unit_counts),
        "unique_contexts": len(context_counts),
        "top_item_types": item_type_counts.most_common(10),
        "top_units": unit_counts.most_common(10),
        "top_disciplines": discipline_counts.most_common(10),
        "top_contexts": context_counts.most_common(10),
    }


def _build_prompt(pair: TrainingPair, methodology_context: str) -> str:
    sections = [
        "Eres un asistente de presupuestos de obra.",
        "Devuelve la partida más probable para la entrada dada y conserva el formato de salida.",
    ]
    if methodology_context:
        sections.append("Contexto metodológico de referencia:\n" + methodology_context[:3500])
    sections.append(
        "Entrada:\n"
        f"- tipo_detectado: {pair.input_item_type}\n"
        f"- unidad_detectada: {pair.input_unit or '?'}\n"
        f"- contexto: {pair.input_context}"
    )
    sections.append(
        "Salida esperada en JSON con code, description, unit, quantity y price."
    )
    return "\n\n".join(sections)


def _example_to_record(
    pair: TrainingPair,
    *,
    split: str,
    record_index: int,
    methodology_context: str,
) -> Day2DatasetRecord:
    prompt = _build_prompt(pair, methodology_context)
    return Day2DatasetRecord(
        record_id=f"{split}_{record_index:04d}",
        split=split,
        input_item_type=pair.input_item_type,
        input_unit=pair.input_unit,
        input_context=pair.input_context,
        prompt=prompt,
        target_code=pair.output_bc3_code,
        target_description=pair.output_description,
        target_unit=pair.output_unit,
        target_quantity=pair.output_quantity,
        target_price=pair.output_price,
        target_amount=pair.output_quantity * pair.output_price,
    )


def _records_to_jsonl(records: list[Day2DatasetRecord]) -> list[str]:
    return [json.dumps(asdict(record), ensure_ascii=False) for record in records]


def build_day2_dataset_artifacts(
    pres_path: str | Path | list[str | Path],
    output_dir: str | Path,
    *,
    validation_limit: int = 40,
    min_source_quality: float = 0.75,
) -> dict[str, Any]:
    """Build a Day 2 supervised dataset bundle and persist it to disk."""
    pres_paths = _resolve_pres_paths(pres_path)
    if not pres_paths:
        raise FileNotFoundError("No PRES sources provided")

    output_dir = Path(output_dir).resolve()
    for path in pres_paths:
        if not path.exists():
            raise FileNotFoundError(f"PRES source not found: {path}")

    pairs: list[TrainingPair] = []
    source_pair_counts: dict[str, int] = {}
    source_quality_scores: dict[str, float] = {}
    excluded_sources: dict[str, str] = {}
    for path in pres_paths:
        extracted = extract_training_pairs(path)
        quality = _source_quality_score(extracted)
        source_quality_scores[str(path)] = round(quality, 4)
        if extracted and quality < min_source_quality:
            excluded_sources[str(path)] = (
                f"quality {quality:.2f} below threshold {min_source_quality:.2f}"
            )
            continue
        for pair in extracted:
            pair.source = path.name
        source_pair_counts[str(path)] = len(extracted)
        pairs.extend(extracted)

    if not pairs:
        raise ValueError("No usable training pairs after source quality filtering")

    validation_pairs = select_validation_pairs(pairs, validation_limit)
    validation_keys = {_pair_key(pair) for pair in validation_pairs}
    train_pairs = [
        pair for pair in sorted(pairs, key=_pair_sort_key) if _pair_key(pair) not in validation_keys
    ]

    methodology_context = generate_methodology_context(training_pairs=pairs)
    summary = summarize_training_pairs(pairs)

    train_records = [
        _example_to_record(
            pair,
            split="train",
            record_index=index + 1,
            methodology_context=methodology_context,
        )
        for index, pair in enumerate(train_pairs)
    ]
    validation_records = [
        _example_to_record(
            pair,
            split="validation",
            record_index=index + 1,
            methodology_context=methodology_context,
        )
        for index, pair in enumerate(validation_pairs)
    ]

    output_dir.mkdir(parents=True, exist_ok=True)

    train_path = output_dir / "day2_train.jsonl"
    validation_path = output_dir / "day2_validation.jsonl"
    manifest_path = output_dir / "day2_training_manifest.json"
    report_path = output_dir / "day2_training_report.md"

    train_path.write_text(
        "\n".join(_records_to_jsonl(train_records)) + ("\n" if train_records else ""),
        encoding="utf-8",
    )
    validation_path.write_text(
        "\n".join(_records_to_jsonl(validation_records)) + ("\n" if validation_records else ""),
        encoding="utf-8",
    )

    manifest = {
        "pres_path": str(pres_paths[0]),
        "pres_paths": [str(path) for path in pres_paths],
        "source_pair_counts": source_pair_counts,
        "source_quality_scores": source_quality_scores,
        "excluded_sources": excluded_sources,
        "validation_limit": validation_limit,
        "min_source_quality": min_source_quality,
        "summary": summary,
        "methodology_chars": len(methodology_context),
        "train_records": len(train_records),
        "validation_records": len(validation_records),
        "train_path": str(train_path),
        "validation_path": str(validation_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    report_lines = [
        "# Day 2 training dataset report",
        "",
        f"- PRES sources: {len(pres_paths)}",
        f"- Primary source: `{pres_paths[0]}`",
        f"- Validation limit: {validation_limit}",
        f"- Min source quality: {min_source_quality:.2f}",
        f"- Total pairs extracted: {summary['total_pairs']}",
        f"- Train records: {len(train_records)}",
        f"- Validation records: {len(validation_records)}",
        f"- Methodology context chars: {len(methodology_context)}",
        "",
        "## Top item types",
        "",
        *(_format_counter_rows(summary["top_item_types"])),
        "",
        "## Top disciplines",
        "",
        *(_format_counter_rows(summary["top_disciplines"])),
        "",
        "## Source pair counts",
        "",
        *(_format_counter_rows(list(source_pair_counts.items()))),
        "",
        "## Source quality scores",
        "",
        *(_format_counter_rows([(k, int(v * 100)) for k, v in source_quality_scores.items()])),
        "",
        "## Validation examples",
        "",
        "| record_id | item_type | context | target_code | target_unit |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in validation_records[:12]:
        report_lines.append(
            f"| {_md_cell(record.record_id)} | {_md_cell(record.input_item_type)} | {_md_cell(record.input_context)} | {_md_cell(record.target_code)} | {_md_cell(record.target_unit)} |"
        )

    if excluded_sources:
        report_lines.extend([
            "",
            "## Excluded sources",
            "",
        ])
        for source_path, reason in excluded_sources.items():
            report_lines.append(f"- {source_path}: {reason}")
    report_lines.extend(
        [
            "",
            "## Dataset bundle",
            "",
            f"- Train JSONL: `{train_path}`",
            f"- Validation JSONL: `{validation_path}`",
            f"- Manifest: `{manifest_path}`",
        ]
    )
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    manifest["manifest_path"] = str(manifest_path)
    manifest["report_path"] = str(report_path)
    return _json_safe(manifest)