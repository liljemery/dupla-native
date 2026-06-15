"""
BC3 (FIEBDC-3) writer for Presto 8.8 compatible budget export.

Follows the FIEBDC-3/2020 specification:
  - ~V: version with FORMAT_VERSION, CHARSET=ANSI, INFO_TYPE=2 (budget)
  - ~K: regional config (DOP currency)
  - ~C: root (##), chapters (#), partidas (no suffix)
  - ~D: decomposition hierarchy
  - ~M: measurements with PARENT_CODE\\CHILD_CODE | POSITION | TOTAL | lines
  - ~T: long text descriptions
  - Codes max 13 chars (Presto 8.8 limit)
  - Encoding: cp1252 (ANSI)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from core.schemas import BudgetRow, ProjectContext

logger = logging.getLogger("dupla.export_bc3")

_PRESTO_MAX_CODE_LEN = 13


def _escape_bc3(text: str) -> str:
    return text.replace("|", "/").replace("\\", "/").replace("~", "-").replace("\n", " ").strip()


def _format_price(value: Any) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return ""


def _coerce_row(row: BudgetRow | Mapping[str, object]) -> BudgetRow:
    if isinstance(row, BudgetRow):
        return row
    payload = dict(row)
    return BudgetRow(
        row_type=str(payload.get("row_type", "line")),
        code=str(payload.get("code", "")),
        nat=str(payload.get("nat", "")),
        unit=str(payload.get("unit", "")),
        summary=str(payload.get("summary", "")),
        quantity=payload.get("quantity"),
        unit_price=payload.get("unit_price"),
        amount=payload.get("amount"),
        chapter_id=payload.get("chapter_id"),
        parent_chapter_id=payload.get("parent_chapter_id"),
        level=int(payload.get("level", 0) or 0),
        takeoff_key=payload.get("takeoff_key"),
        source_refs=list(payload.get("source_refs", [])),
        assumptions=list(payload.get("assumptions", [])),
        metadata=dict(payload.get("metadata", {})),
        excel_row=payload.get("excel_row"),
    )


def _sanitize_code(code: str, max_len: int = _PRESTO_MAX_CODE_LEN) -> str:
    """Strip FIEBDC-invalid chars and fit within Presto's 13-char limit."""
    clean = code.replace("#", "").replace("|", "").replace(" ", "_").strip()
    if clean.startswith("DUP-CH-"):
        num = clean.replace("DUP-CH-", "").split("-", 1)[0]
        clean = f"C{num}"
    elif clean.startswith("DUP-"):
        clean = clean.replace("DUP-", "D")
    return clean[:max_len]


def export_budget_bc3(
    context: ProjectContext,
    rows: list[BudgetRow | Mapping[str, object]],
    output_path: str | Path,
    *,
    bc3_catalog: dict[str, Any] | None = None,
) -> Path:
    """
    Export a Dupla budget to BC3 (FIEBDC-3/2020) format for Presto 8.8.

    When *bc3_catalog* is provided, partidas that match a catalog code get their
    full APU decomposition (~D with materials/labor/equipment components) copied
    into the exported file so Presto displays the cost analysis.
    """
    coerced_rows = [_coerce_row(r) for r in rows]
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    project_name = _escape_bc3(context.project_name or context.project_id or "DUPLA")
    root_code = _sanitize_code(context.project_id or "DUPLA")
    today = datetime.now().strftime("%d%m%Y")

    # -- Classify rows --
    chapters: list[BudgetRow] = []
    lines_by_chapter: dict[str, list[BudgetRow]] = {}
    all_line_codes: set[str] = set()

    for row in coerced_rows:
        if row.row_type == "chapter":
            chapters.append(row)
            ch_id = row.chapter_id or row.code
            lines_by_chapter.setdefault(ch_id, [])
        elif row.row_type == "line":
            ch_id = row.chapter_id or "ROOT"
            lines_by_chapter.setdefault(ch_id, []).append(row)
            all_line_codes.add(_sanitize_code(row.code))

    # -- Build chapter hierarchy for ~D and ~M POSITION --
    # top_chapters: direct children of root (level 1 or no parent)
    # sub_chapters: children of a top chapter (level 2+)
    top_chapter_ids: list[str] = []
    children_of: dict[str, list[str]] = {}

    for ch in chapters:
        ch_id = ch.chapter_id or ch.code
        parent = ch.parent_chapter_id
        if parent:
            children_of.setdefault(parent, []).append(ch_id)
        else:
            top_chapter_ids.append(ch_id)

    # Position index: chapter_id -> 1-based position among siblings
    chapter_position: dict[str, int] = {}
    for idx, ch_id in enumerate(top_chapter_ids, start=1):
        chapter_position[ch_id] = idx
    for parent_id, kids in children_of.items():
        for idx, kid_id in enumerate(kids, start=1):
            chapter_position[kid_id] = idx

    # Leaf chapters: those that directly contain line items
    leaf_chapters: dict[str, str] = {}
    for ch in chapters:
        ch_id = ch.chapter_id or ch.code
        if lines_by_chapter.get(ch_id):
            leaf_chapters[ch_id] = _sanitize_code(ch.code)

    # -- Build position path for each leaf chapter --
    # Walk up from leaf to root to build the POSITION path (e.g. "1\2")
    chapter_parent_map: dict[str, str | None] = {}
    for ch in chapters:
        ch_id = ch.chapter_id or ch.code
        chapter_parent_map[ch_id] = ch.parent_chapter_id

    def _position_path(chapter_id: str) -> str:
        parts: list[str] = []
        current: str | None = chapter_id
        while current and current in chapter_position:
            parts.append(str(chapter_position[current]))
            current = chapter_parent_map.get(current)
        parts.reverse()
        return "\\".join(parts)

    records: list[str] = []

    # ==================== ~V ====================
    # Spec: ~V|FILE_OWNERSHIP|FORMAT_VERSION\DDMMYYYY|EMISSION_PROGRAM|HEADER\LABELS|CHARSET|COMMENT|INFO_TYPE|
    records.append(f"~V|DUPLA|FIEBDC-3/2016\\{today}|DUPLA||ANSI||2|")

    # ==================== ~K ====================
    # Spec field 1: DN\DD\DS\DR\DI\DP\DC\DM\CURRENCY
    records.append("~K|\\2\\2\\2\\3\\2\\2\\2\\2\\DOP\\|0|")

    # ==================== ~C records ====================
    # Root (##)
    records.append(f"~C|{root_code}##||{project_name}|||0|")

    # Chapters (#)
    chapter_code_map: dict[str, str] = {}
    for ch in chapters:
        ch_id = ch.chapter_id or ch.code
        ch_code = _sanitize_code(ch.code)
        chapter_code_map[ch_id] = ch_code
        records.append(f"~C|{ch_code}#||{_escape_bc3(ch.summary)}|||0|")

    # Line items (no suffix)
    emitted_codes: set[str] = {root_code}
    emitted_codes.update(chapter_code_map.values())

    emitted_line_codes: set[str] = set()
    for row in coerced_rows:
        if row.row_type != "line":
            continue
        code = _sanitize_code(row.code)
        if code in emitted_line_codes:
            continue
        emitted_line_codes.add(code)
        unit = _escape_bc3(row.unit or "")
        summary = _escape_bc3(row.summary or "")
        price_value = row.unit_price
        if isinstance(price_value, str) and price_value.startswith("="):
            price_value = None
        records.append(f"~C|{code}|{unit}|{summary}|{_format_price(price_value)}|{today}|0|")
        emitted_codes.add(code)

    # ==================== APU component ~C records ====================
    hierarchy = (bc3_catalog or {}).get("hierarchy", {})
    concepts = (bc3_catalog or {}).get("concepts_by_code", {})
    apu_decomp_records: list[str] = []

    def _collect_component_tree(parent_code: str) -> None:
        """Recursively emit ~C for components and ~D for decompositions."""
        children = hierarchy.get(parent_code, [])
        if not children:
            return
        tokens: list[str] = []
        for child in children:
            child_code = str(child.get("code", "")).strip()
            if not child_code:
                continue
            factor = child.get("factor")
            yield_val = child.get("yield")
            f_str = f"{float(factor):.4g}" if factor is not None else "1"
            y_str = f"{float(yield_val):.4g}" if yield_val is not None else "1"
            tokens.append(f"{child_code}\\{f_str}\\{y_str}")

            if child_code not in emitted_codes:
                emitted_codes.add(child_code)
                concept = concepts.get(child_code, {})
                c_unit = _escape_bc3(str(concept.get("unit", "")))
                c_summary = _escape_bc3(str(concept.get("summary", "")))
                c_price = _format_price(concept.get("price"))
                c_date = str(concept.get("date", today))
                c_type = str(concept.get("type", "0"))
                records.append(
                    f"~C|{child_code}|{c_unit}|{c_summary}|{c_price}|{c_date}|{c_type}|"
                )
                _collect_component_tree(child_code)

        if tokens:
            joined_tokens = "\\".join(tokens)
            apu_decomp_records.append(
                f"~D|{parent_code}|{joined_tokens}\\|"
            )

    emitted_measurement_codes: set[str] = set()
    for row in coerced_rows:
        if row.row_type != "line":
            continue
        line_code = _sanitize_code(row.code)
        raw_code = row.code.replace("#", "").strip()
        catalog_code = raw_code if raw_code in hierarchy else line_code
        if catalog_code in hierarchy:
            _collect_component_tree(catalog_code)

    # ==================== ~D records ====================
    # Root## → top-level chapters
    if top_chapter_ids:
        tokens = "\\".join(
            f"{chapter_code_map[ch_id]}\\1\\1" for ch_id in top_chapter_ids
            if ch_id in chapter_code_map
        )
        if tokens:
            records.append(f"~D|{root_code}##|{tokens}\\|")

    # Parent chapters → sub-chapters + line items
    for ch in chapters:
        ch_id = ch.chapter_id or ch.code
        ch_code = chapter_code_map[ch_id]

        child_tokens: list[str] = []

        # Sub-chapter children
        for kid_id in children_of.get(ch_id, []):
            if kid_id in chapter_code_map:
                child_tokens.append(f"{chapter_code_map[kid_id]}\\1\\1")

        # Line item children
        for line in lines_by_chapter.get(ch_id, []):
            child_tokens.append(f"{_sanitize_code(line.code)}\\1\\1")

        if child_tokens:
            joined_child_tokens = "\\".join(child_tokens)
            records.append(f"~D|{ch_code}#|{joined_child_tokens}\\|")

    # ==================== APU ~D records (partida → components) ====================
    records.extend(apu_decomp_records)

    # ==================== ~M records ====================
    # Spec: ~M|[PARENT_CODE\]CHILD_CODE|{POSITION\}|TOTAL_MEASUREMENT|{TYPE\COMMENT\UNITS\LENGTH\LATITUDE\HEIGHT\}|[LABEL]|
    for ch in chapters:
        ch_id = ch.chapter_id or ch.code
        ch_code = chapter_code_map.get(ch_id, "")
        pos_path = _position_path(ch_id)
        child_lines = lines_by_chapter.get(ch_id, [])

        for line_idx, row in enumerate(child_lines, start=1):
            code = _sanitize_code(row.code)
            qty = row.quantity
            if isinstance(qty, str) and qty.startswith("="):
                continue
            if qty is None:
                continue
            try:
                qty_float = float(qty)
            except (TypeError, ValueError):
                continue

            comment = _escape_bc3(row.summary[:64]) if row.summary else ""

            # PARENT\CHILD
            field1 = f"{ch_code}\\{code}"
            # POSITION: chapter path + line position within chapter
            field2 = f"{pos_path}\\{line_idx}" if pos_path else str(line_idx)
            # TOTAL_MEASUREMENT
            field3 = f"{qty_float:.3f}"
            # Measurement line: TYPE\COMMENT\UNITS\LENGTH\LATITUDE\HEIGHT
            # Put qty in UNITS, leave LENGTH/LATITUDE/HEIGHT empty (= ignored, not zero)
            field4 = f"\\{comment}\\{qty_float:.3f}\\\\\\".rstrip("\\") + "\\"

            records.append(f"~M|{field1}|{field2}|{field3}|{field4}|")

    # ==================== ~T records ====================
    for ch in chapters:
        ch_id = ch.chapter_id or ch.code
        ch_code = chapter_code_map.get(ch_id, "")
        path_info = ch.metadata.get("path", [])
        if path_info:
            long_text = " > ".join(str(p) for p in path_info)
            records.append(f"~T|{ch_code}#|{_escape_bc3(long_text)}|")

    bc3_content = "\n".join(records) + "\n"
    output.write_text(bc3_content, encoding="cp1252", errors="replace")
    logger.info(
        "BC3 exported: %s (%d records, %d chapters, %d lines)",
        output, len(records), len(chapters), len(all_line_codes),
    )
    return output
