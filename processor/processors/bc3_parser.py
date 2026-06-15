"""
Reusable BC3 (FIEBDC) parser.

The active pipeline uses BC3 files as a catalog source for candidate budget
matching, so this module exposes a library function instead of relying on
hardcoded local paths or ad-hoc report generation.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _split_records(raw_text: str) -> list[str]:
    records: list[str] = []
    current = ""

    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("~"):
            if current:
                records.append(current)
            current = stripped
        else:
            current += stripped

    if current:
        records.append(current)

    return records


def _to_float(value: str) -> float | None:
    cleaned = value.strip().replace(",", ".")
    if not cleaned:
        return None

    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_concepts(records: list[str]) -> dict[str, dict[str, Any]]:
    concepts: dict[str, dict[str, Any]] = {}

    for record in records:
        if not record.startswith("~C|"):
            continue

        parts = record[3:].split("|")
        code_field = parts[0].strip() if parts else ""
        if not code_field:
            continue

        code = code_field.split("#", 1)[0].strip()
        parents = code_field.split("#", 1)[1].strip() if "#" in code_field else ""
        unit = parts[1].strip() if len(parts) > 1 else ""
        summary = parts[2].strip() if len(parts) > 2 else ""
        price = _to_float(parts[3]) if len(parts) > 3 else None
        date = parts[4].strip() if len(parts) > 4 else ""
        concept_type = parts[5].strip() if len(parts) > 5 else ""

        concepts[code] = {
            "code": code,
            "parents": parents,
            "unit": unit,
            "summary": summary,
            "price": price if price is not None else 0.0,
            "date": date,
            "type": concept_type,
        }

    return concepts


def _parse_decomposition_tokens(tokens: list[str]) -> list[tuple[str, float | None, float | None]]:
    """Parse ~D child tokens: code, optional factor, optional yield (FIEBDC stride 3)."""
    children: list[tuple[str, float | None, float | None]] = []
    index = 0
    while index < len(tokens):
        child_code = tokens[index].replace("#", "").strip()
        if not child_code:
            index += 1
            continue
        factor = _to_float(tokens[index + 1]) if index + 1 < len(tokens) else None
        yield_value = _to_float(tokens[index + 2]) if index + 2 < len(tokens) else None
        children.append((child_code, factor, yield_value))
        index += 3 if index + 2 < len(tokens) else 1
    return children


def _iter_decomposition_child_edges(records: list[str]) -> list[tuple[str, str]]:
    """Direct (parent_code, child_code) edges from ~D decomposition lines."""
    edges: list[tuple[str, str]] = []

    for record in records:
        if not record.startswith("~D|"):
            continue

        parts = record[3:].split("|")
        if len(parts) < 2:
            continue

        parent_code = parts[0].replace("#", "").strip()
        tokens = [token.strip() for token in parts[1].split("\\") if token.strip()]
        if not parent_code or not tokens:
            continue

        for child_code, _, _ in _parse_decomposition_tokens(tokens):
            if child_code:
                edges.append((parent_code, child_code))

    return edges


def _parse_hierarchy(records: list[str]) -> dict[str, list[dict[str, Any]]]:
    hierarchy: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for record in records:
        if not record.startswith("~D|"):
            continue

        parts = record[3:].split("|")
        if len(parts) < 2:
            continue

        parent_code = parts[0].replace("#", "").strip()
        tokens = [token.strip() for token in parts[1].split("\\") if token.strip()]
        if not parent_code or not tokens:
            continue

        for child_code, factor, yield_value in _parse_decomposition_tokens(tokens):
            hierarchy[parent_code].append(
                {
                    "code": child_code,
                    "factor": factor,
                    "yield": yield_value,
                }
            )

    return hierarchy


def _parse_decomposition_parent_candidates(records: list[str]) -> dict[str, list[str]]:
    """
    For each component code, BC3 files that list which ~D parents reference it.

    Used to walk upward from a priced line toward chapter-like headers in the same file.
    Multiple parents are preserved (e.g. shared resources); callers disambiguate.
    """
    buckets: dict[str, list[str]] = defaultdict(list)
    seen_pairs: set[tuple[str, str]] = set()

    for parent_code, child_code in _iter_decomposition_child_edges(records):
        key = (parent_code, child_code)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        buckets[child_code].append(parent_code)

    return dict(buckets)


def _parse_texts(records: list[str]) -> dict[str, str]:
    texts: dict[str, str] = {}

    for record in records:
        if not record.startswith("~T|"):
            continue

        parts = record[3:].split("|")
        if len(parts) < 2:
            continue

        code = parts[0].replace("#", "").strip()
        text = parts[1].strip()
        if code and text:
            texts[code] = text

    return texts


def _parse_measurements(records: list[str]) -> dict[str, list[dict[str, str]]]:
    measurements: dict[str, list[dict[str, str]]] = defaultdict(list)

    for record in records:
        if not record.startswith("~M|"):
            continue

        parts = record[3:].split("|")
        if not parts:
            continue

        codes = parts[0].strip()
        if "#" in codes:
            parent, child = codes.split("#", 1)
        else:
            parent, child = codes, ""

        measurements[parent.strip()].append(
            {
                "child": child.strip(),
                "raw": "|".join(parts[1:]).strip(),
            }
        )

    return measurements


def parse_bc3(path: str) -> dict[str, Any]:
    """
    Parse a BC3 file into a reusable normalized structure.

    Args:
        path: Absolute or relative path to the BC3 file.

    Returns:
        Dictionary with concepts, priced items, chapters, hierarchy and texts.
    """
    bc3_path = Path(path)
    raw_text = bc3_path.read_text(encoding="latin-1", errors="replace")
    records = _split_records(raw_text)

    concepts = _parse_concepts(records)
    origin = bc3_path.name
    for concept in concepts.values():
        concept["bc3_origin"] = origin

    hierarchy = _parse_hierarchy(records)
    decomposition_parent_candidates = _parse_decomposition_parent_candidates(records)
    texts = _parse_texts(records)
    measurements = _parse_measurements(records)

    items: list[dict[str, Any]] = []
    chapters: list[dict[str, Any]] = []

    for concept in concepts.values():
        enriched = {
            **concept,
            "long_text": texts.get(concept["code"], ""),
            "children": hierarchy.get(concept["code"], []),
            "bc3_origin": origin,
        }

        if enriched["unit"] and float(enriched.get("price", 0) or 0) > 0:
            items.append(enriched)
        elif enriched["summary"]:
            chapters.append(enriched)

    items.sort(key=lambda item: item["code"])
    chapters.sort(key=lambda chapter: chapter["code"])

    return {
        "file": bc3_path.name,
        "path": str(bc3_path),
        "record_count": len(records),
        "concept_count": len(concepts),
        "chapter_count": len(chapters),
        "item_count": len(items),
        "concepts_by_code": concepts,
        "chapters": chapters,
        "items": items,
        "hierarchy": hierarchy,
        "decomposition_parent_candidates": decomposition_parent_candidates,
        "texts": texts,
        "measurements": measurements,
    }


def merge_bc3_catalogs(*catalogs: dict[str, Any]) -> dict[str, Any]:
    """
    Combine several ``parse_bc3`` payloads into one catalog.

    Each priced ``item`` keeps its ``bc3_origin`` (source BC3 filename). ``items`` lists
    are concatenated so embeddings can represent all sources. ``concepts_by_code`` uses
    first-seen code; if the same code appears again with a different summary/price, the
    duplicate is recorded on ``bc3_origin_alternates`` on the kept concept.
    """
    if not catalogs:
        return {}
    if len(catalogs) == 1:
        return dict(catalogs[0])

    merged_items: list[dict[str, Any]] = []
    merged_chapters: list[dict[str, Any]] = []
    merged_concepts: dict[str, dict[str, Any]] = {}
    merged_hierarchy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    merged_texts: dict[str, str] = {}
    merged_measurements: dict[str, list[dict[str, str]]] = defaultdict(list)
    merged_decomp: dict[str, list[str]] = defaultdict(list)
    origins: list[str] = []

    for cat in catalogs:
        origin = str(cat.get("file") or Path(str(cat.get("path", ""))).name or "unknown.bc3")
        origins.append(origin)
        for item in cat.get("items") or []:
            it = dict(item)
            it.setdefault("bc3_origin", origin)
            merged_items.append(it)
        for ch in cat.get("chapters") or []:
            c = dict(ch)
            c.setdefault("bc3_origin", origin)
            merged_chapters.append(c)
        for code, concept in (cat.get("concepts_by_code") or {}).items():
            c0 = dict(concept)
            c0.setdefault("bc3_origin", origin)
            if code not in merged_concepts:
                merged_concepts[code] = c0
            else:
                prev = merged_concepts[code]
                same = (
                    str(prev.get("summary", "")).strip() == str(c0.get("summary", "")).strip()
                    and float(prev.get("price") or 0) == float(c0.get("price") or 0)
                )
                if same:
                    continue
                alts = prev.setdefault("bc3_origin_alternates", [])
                alts.append(
                    {
                        "bc3_origin": origin,
                        "summary": c0.get("summary", ""),
                        "price": c0.get("price", 0),
                        "unit": c0.get("unit", ""),
                    }
                )
        for parent, rows in (cat.get("hierarchy") or {}).items():
            merged_hierarchy[parent].extend(rows)
        for code, text in (cat.get("texts") or {}).items():
            merged_texts[code] = text
        for parent, rows in (cat.get("measurements") or {}).items():
            merged_measurements[parent].extend(rows)
        for child, parents in (cat.get("decomposition_parent_candidates") or {}).items():
            bucket = merged_decomp[child]
            seen_parents = set(bucket)
            for p in parents:
                if p not in seen_parents:
                    bucket.append(p)
                    seen_parents.add(p)

    merged_items.sort(key=lambda x: (str(x.get("code", "")), str(x.get("bc3_origin", ""))))
    merged_chapters.sort(key=lambda x: (str(x.get("code", "")), str(x.get("bc3_origin", ""))))

    return {
        "file": "|".join(origins),
        "path": "|".join(str(c.get("path", "")) for c in catalogs),
        "record_count": sum(int(c.get("record_count", 0) or 0) for c in catalogs),
        "concept_count": len(merged_concepts),
        "chapter_count": len(merged_chapters),
        "item_count": len(merged_items),
        "concepts_by_code": merged_concepts,
        "chapters": merged_chapters,
        "items": merged_items,
        "hierarchy": dict(merged_hierarchy),
        "decomposition_parent_candidates": dict(merged_decomp),
        "texts": merged_texts,
        "measurements": dict(merged_measurements),
    }


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse a BC3 file into JSON.")
    parser.add_argument("path", help="Path to the BC3 file")
    parser.add_argument(
        "--output",
        help="Optional output JSON path. Prints to stdout if omitted.",
    )
    return parser


if __name__ == "__main__":
    args = _build_cli().parse_args()
    parsed = parse_bc3(args.path)
    payload = json.dumps(parsed, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"BC3 parse written to {args.output}")
    else:
        print(payload)
