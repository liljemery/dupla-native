"""
ConstruCosto price database loader and fuzzy matcher.

Parses the four ConstruCosto CSV exports (Punta Cana zone) and exposes a
snapshot that the budget composer can query by description + unit to resolve
unit prices for Dominican construction projects.

CSV sources (all RD$, Punta Cana):
  - Analisis de Costos:   complete APUs with code, unit, and per-unit price
  - Materiales e Insumos: raw material unit prices
  - Mano de Obra:         labor jornales and brigade rates
  - Equipos y Mov Tierra: equipment hourly rates
"""

from __future__ import annotations

import csv
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

import openpyxl

logger = logging.getLogger("dupla.pricing")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ConstrucostoEntry:
    code: str
    description: str
    unit: str
    unit_price: float          # RD$ without ITBIS
    unit_price_with_tax: float # RD$ with ITBIS
    category: str
    source: str                # which CSV it came from
    tokens: list[str] = field(default_factory=list, repr=False)


@dataclass
class ConstrucostoSnapshot:
    entries: list[ConstrucostoEntry] = field(default_factory=list)
    by_code: dict[str, ConstrucostoEntry] = field(default_factory=dict)
    source_dir: str = ""

    @property
    def count(self) -> int:
        return len(self.entries)


# ---------------------------------------------------------------------------
# Text normalization (accent-safe, construction-domain)
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[^a-z0-9/. ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_STOPWORDS = frozenset({
    "de", "del", "en", "la", "el", "las", "los", "un", "una", "con",
    "para", "por", "sin", "sobre", "todo", "costo", "incluye", "mas",
    "hasta", "que", "se", "no", "es", "al", "lo",
})


def _tokenize(text: str) -> list[str]:
    normalized = _normalize(text)
    return [tok for tok in normalized.split() if len(tok) > 1 and tok not in _STOPWORDS]


# ---------------------------------------------------------------------------
# RD$ price parsing
# ---------------------------------------------------------------------------

_RD_RE = re.compile(r"RD\$\s*([\d,]+(?:\.\d+)?)")


def _parse_rdprice(raw: str) -> float:
    """Parse 'RD$88,983.05' → 88983.05.  Returns 0.0 on failure."""
    if not raw or not isinstance(raw, str):
        if isinstance(raw, (int, float)):
            return float(raw)
        return 0.0
    match = _RD_RE.search(raw.strip())
    if match:
        return float(match.group(1).replace(",", ""))
    # Fallback to direct float parse if no RD$ prefix
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return 0.0

def _read_rows(path: Path) -> Iterator[Sequence[Any]]:
    """Yield rows from a CSV or XLSX file."""
    if path.suffix.lower() == ".xlsx":
        wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
        ws = wb.active
        for row in ws.iter_rows(values_only=True):
            yield ["" if v is None else str(v) for v in row]
    else:
        with open(path, encoding="latin-1", newline="") as fh:
            reader = csv.reader(fh)
            for row in reader:
                yield row


# ---------------------------------------------------------------------------
# CSV parsers (one per ConstruCosto export type)
# ---------------------------------------------------------------------------

def _parse_analisis(path: Path) -> list[ConstrucostoEntry]:
    """Parse 'Analisis de Costos' — main APU file with per-unit prices."""
    entries: list[ConstrucostoEntry] = []
    current_category = ""

    iterator = _read_rows(path)
    next(iterator, None)  # skip header
    for row in iterator:
        if len(row) < 9:
            continue
        code = (row[0] or "").strip()
        desc = (row[1] or "").strip()
        unit = (row[3] or "").strip()
        subtotal_raw = row[6] if len(row) > 6 else ""
        total_raw = row[8] if len(row) > 8 else ""

        if not desc:
            continue

        # Category headers: code like "100.00" with no price
        if code and code.endswith(".00") and not _parse_rdprice(subtotal_raw):
            current_category = desc
            continue

        # Partida rows: have a code (e.g. "100.01") and a price
        if not code:
            continue

        price_net = _parse_rdprice(subtotal_raw)
        price_gross = _parse_rdprice(total_raw)
        if price_net <= 0 and price_gross <= 0:
            continue

        entry = ConstrucostoEntry(
            code=code,
            description=desc,
            unit=unit.upper(),
            unit_price=price_net,
            unit_price_with_tax=price_gross,
            category=current_category,
            source="analisis",
            tokens=_tokenize(desc),
        )
        entries.append(entry)

    logger.info("Parsed %d APU entries from %s", len(entries), path.name)
    return entries


def _parse_materiales(path: Path) -> list[ConstrucostoEntry]:
    """Parse 'Materiales e Insumos' — raw material prices."""
    entries: list[ConstrucostoEntry] = []
    current_category = ""

    iterator = _read_rows(path)
    next(iterator, None)
    for row in iterator:
        if len(row) < 5:
            continue
        desc = (row[1] or "").strip()
        unit = (row[2] or "").strip()
        price_gross_raw = row[3] if len(row) > 3 else ""
        price_net_raw = row[4] if len(row) > 4 else ""

        if not desc:
            continue

        # Category headers are all-caps with no price
        if not unit and desc.isupper():
            current_category = desc
            continue

        price_net = _parse_rdprice(price_net_raw)
        price_gross = _parse_rdprice(price_gross_raw)
        if price_net <= 0 and price_gross <= 0:
            continue

        entry = ConstrucostoEntry(
            code="",
            description=desc,
            unit=unit.upper(),
            unit_price=price_net or price_gross,
            unit_price_with_tax=price_gross or price_net,
            category=current_category,
            source="materiales",
            tokens=_tokenize(desc),
        )
        entries.append(entry)

    logger.info("Parsed %d material entries from %s", len(entries), path.name)
    return entries


def _parse_mano_obra(path: Path) -> list[ConstrucostoEntry]:
    """Parse 'Mano de Obra' — labor rates and brigade costs."""
    entries: list[ConstrucostoEntry] = []
    current_category = ""

    for row in _read_rows(path):
        if len(row) < 4:
            continue

        code = (row[0] or "").strip()
        desc = (row[1] or "").strip()
        unit = (row[2] or "").strip()
        price_raw = row[3] if len(row) > 3 else ""

        if not desc:
            continue

        if code and code.endswith(".00") and not _parse_rdprice(price_raw):
            current_category = desc
            continue

        price = _parse_rdprice(price_raw)
        if price <= 0:
            continue

        entry = ConstrucostoEntry(
            code=code,
            description=desc,
            unit=unit.upper(),
            unit_price=price,
            unit_price_with_tax=price,
            category=current_category,
            source="mano_obra",
            tokens=_tokenize(desc),
        )
        entries.append(entry)

    logger.info("Parsed %d labor entries from %s", len(entries), path.name)
    return entries


def _parse_equipos(path: Path) -> list[ConstrucostoEntry]:
    """Parse 'Equipos y Movimientos de Tierra' — equipment hourly costs."""
    entries: list[ConstrucostoEntry] = []
    current_category = ""

    iterator = _read_rows(path)
    next(iterator, None)
    for row in iterator:
        if len(row) < 9:
            continue

        code = (row[0] or "").strip()
        desc = (row[1] or "").strip()
        unit = (row[3] or "").strip()
        subtotal_raw = row[6] if len(row) > 6 else ""
        total_raw = row[8] if len(row) > 8 else ""

        if not desc:
            continue

        if code and code.endswith(".00") and not _parse_rdprice(subtotal_raw):
            current_category = desc
            continue

        if not code:
            continue

        price_net = _parse_rdprice(subtotal_raw)
        price_gross = _parse_rdprice(total_raw)
        if price_net <= 0 and price_gross <= 0:
            continue

        entry = ConstrucostoEntry(
            code=code,
            description=desc,
            unit=unit.upper(),
            unit_price=price_net,
            unit_price_with_tax=price_gross,
            category=current_category,
            source="equipos",
            tokens=_tokenize(desc),
        )
        entries.append(entry)

    logger.info("Parsed %d equipment entries from %s", len(entries), path.name)
    return entries


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------

_FILE_MAP: dict[str, Any] = {
    "analisis": ("Analisis de Costos*ConstruCosto.*", _parse_analisis),
    "materiales": ("Materiales e Insumos*ConstruCosto.*", _parse_materiales),
    "mano_obra": ("Mano de obra*ConstruCosto.*", _parse_mano_obra),
    "equipos": ("Equipos y Movimientos*ConstruCosto.*", _parse_equipos),
}


def load_construcosto_snapshot(
    directory: str | Path | None = None,
) -> ConstrucostoSnapshot:
    """Load all ConstruCosto CSVs from *directory* into a queryable snapshot.

    If *directory* is None, uses ``data/construcosto`` relative to the repo root.
    """
    if directory is None:
        directory = Path(__file__).resolve().parent.parent / "data" / "construcosto"
    directory = Path(directory)

    snapshot = ConstrucostoSnapshot(source_dir=str(directory))

    for key, (glob_pattern, parser) in _FILE_MAP.items():
        matches = sorted(directory.glob(glob_pattern))
        if not matches:
            logger.warning("ConstruCosto CSV not found: %s in %s", glob_pattern, directory)
            continue
        parsed = parser(matches[0])
        snapshot.entries.extend(parsed)

    for entry in snapshot.entries:
        if entry.code:
            snapshot.by_code[entry.code] = entry

    logger.info(
        "ConstruCosto snapshot loaded: %d entries (%d with code) from %s",
        snapshot.count,
        len(snapshot.by_code),
        directory,
    )
    return snapshot


# ---------------------------------------------------------------------------
# Fuzzy price lookup
# ---------------------------------------------------------------------------

_UNIT_FAMILIES: dict[str, str] = {
    "m2": "area", "mt2": "area",
    "m3": "volume", "mt3": "volume",
    "ml": "length", "m": "length",
    "ud": "count", "und": "count", "un": "count", "u": "count", "pz": "count",
    "pa": "count",
    "kg": "mass", "qq": "mass", "lb": "mass",
    "gl": "liquid", "gls": "liquid",
    "hr": "time", "dia": "time",
    "p2": "lumber",
}


def _unit_family(unit: str) -> str | None:
    return _UNIT_FAMILIES.get(unit.lower().strip())


def _token_score(query_tokens: list[str], entry_tokens: list[str]) -> float:
    """Token overlap with partial substring bonus.

    Exact token matches count 1.0 each; partial containment (one token
    is a substring of another) counts 0.5.  The score is normalized by
    the minimum of the two token-set sizes so that shorter queries still
    score well against longer database descriptions.
    """
    if not query_tokens or not entry_tokens:
        return 0.0
    q_set = set(query_tokens)
    e_set = set(entry_tokens)

    exact = len(q_set & e_set)
    partial = 0.0
    for qt in q_set - e_set:
        for et in e_set:
            if qt in et or et in qt:
                partial += 0.5
                break

    denominator = min(len(q_set), len(e_set))
    return (exact + partial) / denominator if denominator else 0.0


@dataclass
class PriceMatch:
    entry: ConstrucostoEntry
    score: float
    unit_price: float


def find_best_price(
    snapshot: ConstrucostoSnapshot,
    description: str,
    unit: str = "",
    *,
    min_score: float = 0.45,
    prefer_analisis: bool = True,
    allowed_sources: frozenset[str] | None = None,
) -> PriceMatch | None:
    """Find the ConstruCosto entry that best matches *description*.

    Args:
        snapshot: Loaded ConstruCosto data.
        description: Budget line summary / description to match.
        unit: Optional unit for compatibility bonus.
        min_score: Minimum token-overlap score to accept a match.
        prefer_analisis: Give slight bonus to APU (analisis) entries since
            they represent complete cost analyses, not just material prices.
        allowed_sources: If set, only consider entries whose ``source`` is in this set.

    Returns:
        Best ``PriceMatch`` above threshold, or ``None``.
    """
    query_tokens = _tokenize(description)
    if not query_tokens:
        return None

    query_family = _unit_family(unit) if unit else None
    best: PriceMatch | None = None

    for entry in snapshot.entries:
        if allowed_sources is not None and entry.source not in allowed_sources:
            continue
        score = _token_score(query_tokens, entry.tokens)
        if score < min_score:
            continue

        # Bonus for unit compatibility
        if query_family and _unit_family(entry.unit) == query_family:
            score += 0.10

        # Slight preference for complete APU entries
        if prefer_analisis and entry.source == "analisis":
            score += 0.05

        if best is None or score > best.score:
            best = PriceMatch(
                entry=entry,
                score=score,
                unit_price=entry.unit_price,
            )

    return best


def find_prices(
    snapshot: ConstrucostoSnapshot,
    description: str,
    unit: str = "",
    *,
    min_score: float = 0.40,
    top_n: int = 5,
) -> list[PriceMatch]:
    """Return top-N matches above threshold, sorted by score descending."""
    query_tokens = _tokenize(description)
    if not query_tokens:
        return []

    query_family = _unit_family(unit) if unit else None
    matches: list[PriceMatch] = []

    for entry in snapshot.entries:
        score = _token_score(query_tokens, entry.tokens)
        if score < min_score:
            continue

        if query_family and _unit_family(entry.unit) == query_family:
            score += 0.10

        if entry.source == "analisis":
            score += 0.05

        matches.append(PriceMatch(entry=entry, score=score, unit_price=entry.unit_price))

    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:top_n]
