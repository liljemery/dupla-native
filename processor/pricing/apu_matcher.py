"""
Match Dupla QuantityTakeoffs against APUs in a constructor PricingStore.

Strategy (per sprint Day 6-8):
    1. Keyword match (element type + dimensions / qualifiers).
    2. Embedding similarity > 0.85  -- lazy-loaded; not implemented yet.
    3. None -> caller falls back to BC3 catalog price.

This module only implements steps 1 and 3 today. Step 2 is wired as a hook
so it can be filled in on Day 7 without changing the public surface.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from core.schemas import QuantityTakeoff
from knowledge.bc3_embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    _default_embedder,
    _normalize_vector,
    build_query_from_takeoff,
)

from .schemas import APUBreakdown, PricingStore

logger = logging.getLogger("dupla.pricing.apu_matcher")


_EMBEDDING_THRESHOLD = 0.85
_EMBED_CHUNK_SIZE = 128
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "pricing_cache"
_DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent / "output" / "apu_matching_log.txt"


# ---------------------------------------------------------------------------
# Element-type rules
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _ElementRule:
    """One row in the dispatch table for keyword match."""
    name: str                 # logical element class (column, beam, wall_block, ...)
    takeoff_keywords: tuple[str, ...]   # tokens (lowercased) that flag a takeoff
    apu_keywords: tuple[str, ...]       # tokens that flag an APU in the catalog
    dimension_fields: tuple[str, ...]   # inputs to extract for disambiguation
    qualifier_fields: tuple[str, ...]   # inputs whose value should appear in the APU


# Order matters: first match wins.
#
# Each rule answers two questions:
#   * Does this takeoff *belong* to this element class? (takeoff_keywords)
#   * For an APU to be a candidate, what must its description contain? (apu_keywords)
# Then we score candidates by how many dimension + qualifier tokens overlap.
_ELEMENT_RULES: tuple[_ElementRule, ...] = (
    # COLUMNS - match by section. C1=0.30x0.20, C2=0.40x0.20, amarre=0.20x0.20.
    # ``column_type`` ("amarre") is read as a qualifier so it tilts the score
    # toward "COLUMNAS DE AMARRE" when present.
    _ElementRule(
        name="column",
        takeoff_keywords=("column", "columna"),
        apu_keywords=("columna",),
        dimension_fields=("section_width_m", "section_height_m"),
        qualifier_fields=("column_type",),
    ),
    # BEAMS - match by section + beam_type. APU vocab: "amarre", "enrase",
    # "dintel". Beams are written in the APU in cm form ("30x40"), so
    # normalize_section emits both 0.30 and 30 to bridge that.
    _ElementRule(
        name="beam",
        takeoff_keywords=("beam", "viga"),
        apu_keywords=("viga", "dintel"),
        dimension_fields=("section_width_m", "section_height_m"),
        qualifier_fields=("beam_type",),
    ),
    # RENDER (pañete) - must come BEFORE wall_block because takeoffs of type
    # ``wall_finish_plaster`` carry the "wall" token and would otherwise be
    # captured by the wall rule first.
    _ElementRule(
        name="render",
        takeoff_keywords=("panete", "pañete", "render", "plaster"),
        apu_keywords=("panete",),     # PAÑETE strips to "panete"
        dimension_fields=(),
        qualifier_fields=("location",),
    ),
    # WALLS (block) - match by inch thickness + rebar notation. APU vocab:
    # 'BLOQUES DE 8" 3/8 @ 0.40 BNP'. thickness_in accepts numeric ("8"),
    # string ('8"', "8in", "8 pulgadas"); reinforcement_main_bars accepts
    # "3/8@0.40", 'Ø3/8"@0.40', etc.
    _ElementRule(
        name="wall_block",
        takeoff_keywords=("wall", "muro", "block", "bloque"),
        apu_keywords=("muro", "bloque"),
        dimension_fields=("thickness_in", "block_size"),
        qualifier_fields=("reinforcement_main_bars", "reinforcement_stirrups", "block_spec"),
    ),
    # SLABS - match by type token (plana / inclinada / aligerada) + thickness.
    _ElementRule(
        name="slab",
        takeoff_keywords=("slab", "losa"),
        apu_keywords=("losa",),
        dimension_fields=("thickness_m",),
        qualifier_fields=("slab_type",),
    ),
    # FLOORS - match by material qualifier + tile size.
    _ElementRule(
        name="floor",
        takeoff_keywords=("piso", "floor", "porcelanato", "ceramica", "coralina"),
        apu_keywords=("piso", "porcelanato", "ceramica", "coralina"),
        dimension_fields=("tile_size",),
        qualifier_fields=("material", "location"),
    ),
)


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def _norm(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace and punctuation that isn't dimension-relevant."""
    if not text:
        return ""
    text = _strip_accents(text).lower()
    # Keep digits, letters, ".", "/", "x", '"' and "-" so that "0.30x0.20",
    # '3/8"@0.40' and 'h=0.12' survive the pass.
    text = re.sub(r"[^a-z0-9./\"x@=\- ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


_DIM_PAIR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)")
_REBAR_RE = re.compile(
    r"(\d+/\d+)\"?\s*@\s*(\d+(?:\.\d+)?)",   # 3/8"@0.40 or 3/8@40
    re.IGNORECASE,
)
_THICKNESS_INCH_RE = re.compile(r'(\d+)\s*(?:"|in\b|pulgadas?\b)', re.IGNORECASE)


def _meter_forms(value: float) -> set[str]:
    """Return tokens covering a meter value in both metric forms used in APUs.

    >>> sorted(_meter_forms(0.30))
    ['0.3', '0.30', '30']
    >>> sorted(_meter_forms(0.4))
    ['0.4', '0.40', '40']
    """
    out: set[str] = set()
    out.add(f"{value:.2f}".rstrip("0").rstrip("."))
    out.add(f"{value:.2f}")
    out.add(str(int(round(value * 100))))
    return {tok for tok in out if tok}


def normalize_section(value: Any) -> set[str]:
    """Generate the dimension tokens a section value might appear as in an APU.

    Accepts numbers (treated as meters), pair strings (``"0.30x0.20"``,
    ``"30x40"``), inch markers (``'8"'``, ``"8in"``, ``"8 pulgadas"``), and
    free-form strings. Always emits the pair form so beams written ``"30x40"``
    match a takeoff declared as ``0.30 x 0.40``.

    >>> sorted(normalize_section("0.30x0.20"))
    ['0.20', '0.30', '0.30x0.20', '20', '30', '30x20']
    >>> sorted(normalize_section(0.30))
    ['0.3', '0.30', '30']
    >>> sorted(normalize_section('8"'))
    ['8', '8"']
    """
    out: set[str] = set()
    if value is None:
        return out
    if isinstance(value, (int, float)):
        out |= _meter_forms(float(value))
        return out

    s = _norm(str(value))
    if not s:
        return out
    out.add(s)

    # Inch markers: 8", 8in, 8 pulgadas
    for m in _THICKNESS_INCH_RE.finditer(s):
        n = m.group(1)
        out.add(n)
        out.add(f'{n}"')

    # Pair forms: 0.30x0.20 -> {"0.30","0.20","0.30x0.20","30","20","30x20"}
    for m in _DIM_PAIR_RE.finditer(s):
        a, b = m.group(1), m.group(2)
        out.add(a)
        out.add(b)
        out.add(f"{a}x{b}")
        try:
            ai = int(round(float(a) * 100)) if "." in a else int(a)
            bi = int(round(float(b) * 100)) if "." in b else int(b)
            out.add(str(ai))
            out.add(str(bi))
            out.add(f"{ai}x{bi}")
        except ValueError:
            pass

    # Bare decimals (e.g. "0.30")
    for m in re.finditer(r"\b(\d+\.\d+)\b", s):
        try:
            out |= _meter_forms(float(m.group(1)))
        except ValueError:
            pass
    return {t for t in out if t}


def extract_rebar_notation(value: Any) -> set[str]:
    """Pull tokens that capture rebar reinforcement notation.

    Accepts forms like ``'3/8@0.40'``, ``'Ø3/8"@0.40'``, ``'3/8 @ 40'``.
    Returns the gauge alone, the spacing alone, and the combined
    ``gauge@spacing`` literal — so an APU written ``"3/8 @ 0.40"`` matches a
    takeoff declared as ``"Ø3/8@40cm"``.

    >>> sorted(extract_rebar_notation('3/8@0.40'))
    ['0.40', '3/8', '3/8@0.40', '40']
    >>> sorted(extract_rebar_notation('3/8"@0.40 BNP'))
    ['0.40', '3/8', '3/8@0.40', '40']
    >>> extract_rebar_notation(None)
    set()
    """
    out: set[str] = set()
    if value is None:
        return out
    s = _norm(str(value))
    if not s:
        return out
    out.add(s)

    for m in _REBAR_RE.finditer(s):
        gauge, spacing = m.group(1), m.group(2)
        out.add(gauge)
        out.add(spacing)
        out.add(f"{gauge}@{spacing}")
        try:
            f = float(spacing)
            if f < 5:  # 0.40 m form -> add cm form "40"
                out.add(str(int(round(f * 100))))
        except ValueError:
            pass

    # Discard the noisy whole-string token if we already extracted structure.
    if any("@" in t for t in out - {s}):
        out.discard(s)
    return out


# Block thickness equivalences used by the constructor (inches <-> centimetres).
# Sprint S3 Block 4: when a takeoff says "espesor 15 cm" we need to also try
# '6"' / '6 in' tokens because the constructor's APUs are written that way.
_BLOCK_THICKNESS_EQUIV: tuple[tuple[int, int, int], ...] = (
    # (cm,  inches, inches-tight)
    (10, 4, 4),
    (15, 6, 6),
    (20, 8, 8),
    (30, 12, 12),
)


def _parse_takeoff_description(description: str) -> tuple[set[str], set[str]]:
    """Mine the human takeoff_description for dim + qualifier tokens.

    Returns ``(dim_sig, qual_sig)`` — same shape as ``_signature_from_inputs``.
    """
    dim_sig: set[str] = set()
    qual_sig: set[str] = set()
    if not description:
        return dim_sig, qual_sig
    norm = _norm(description)

    # Section pairs (columns/beams) — "0.30×0.20", "0.30x0.20", "30x40".
    dim_sig |= normalize_section(norm)

    # "espesor 15 cm" -> 15, 0.15, plus inch equivalences for blocks.
    m = re.search(r"espesor\s*(\d+(?:\.\d+)?)\s*cm", norm)
    if m:
        try:
            cm_val = float(m.group(1))
            dim_sig.add(str(int(cm_val)))
            dim_sig.add(f"{cm_val/100:.2f}")
            for cm, inches, _ in _BLOCK_THICKNESS_EQUIV:
                if abs(cm - cm_val) < 0.5:
                    dim_sig.add(str(inches))
                    dim_sig.add(f'{inches}"')
        except ValueError:
            pass

    # "bloques 15cm" / "bloque 8" / "bloque 8\""
    for m in re.finditer(r"bloque[s]?\s*(\d+)\s*(cm|in|\")?", norm):
        n = int(m.group(1))
        suf = (m.group(2) or "").lower()
        dim_sig.add(str(n))
        if suf in ("in", '"'):
            dim_sig.add(f'{n}"')
            for cm, inches, _ in _BLOCK_THICKNESS_EQUIV:
                if inches == n:
                    dim_sig.add(str(cm))
        else:  # cm or bare
            for cm, inches, _ in _BLOCK_THICKNESS_EQUIV:
                if cm == n:
                    dim_sig.add(str(inches))
                    dim_sig.add(f'{inches}"')

    # Qualifier keywords that map onto APU vocabulary.
    QUAL_KEYWORDS = (
        "interior", "exterior", "techo", "viga", "caseta",
        "amarre", "enrase", "dintel",
        "plana", "inclinada", "aligerada",
        "porcelanato", "ceramica", "coralina",
        "masonry", "bloque", "bloques",
        "hormigon", "concreto",
    )
    for kw in QUAL_KEYWORDS:
        if kw in norm:
            qual_sig.add(kw)
    return dim_sig, qual_sig


def _signature_from_inputs(
    inputs: Mapping[str, Any] | None,
    dim_fields: tuple[str, ...],
    qual_fields: tuple[str, ...],
) -> tuple[set[str], set[str]]:
    inputs = inputs or {}
    dim_sig: set[str] = set()
    for f in dim_fields:
        dim_sig |= normalize_section(inputs.get(f))

    qual_sig: set[str] = set()
    for f in qual_fields:
        v = inputs.get(f)
        if v is None:
            continue
        # Rebar fields get the structured pass; others stay literal.
        if "reinforcement" in f or "rebar" in f or "stirrups" in f:
            qual_sig |= extract_rebar_notation(v)
        else:
            qual_sig |= {tok for tok in _norm(str(v)).split() if tok}

    # Sprint S3 Block 4: always mine takeoff_description, context_tags, and
    # material_hint so pipeline-emitted takeoffs (which lack the structured
    # column/beam fields) still produce a useful signature.
    desc = str(inputs.get("takeoff_description") or "")
    if desc:
        d_dim, d_qual = _parse_takeoff_description(desc)
        dim_sig |= d_dim
        qual_sig |= d_qual

    for tag in (inputs.get("context_tags") or []):
        t = _norm(str(tag))
        if t:
            qual_sig.add(t)

    mat = inputs.get("material_hint")
    if mat:
        qual_sig.add(_norm(str(mat)))

    return dim_sig, qual_sig


def match_by_keywords(
    haystack: str,
    tokens: set[str],
) -> int:
    """Count how many ``tokens`` appear inside the normalised ``haystack``.

    >>> match_by_keywords('columnas c1 (0.30x0.20)', {'0.30', '0.20', 'amarre'})
    2
    >>> match_by_keywords('viga de amarre 30x40 bnp', {'30x40', 'amarre'})
    2
    """
    if not haystack or not tokens:
        return 0
    return sum(1 for t in tokens if t and t in haystack)


# ---------------------------------------------------------------------------
# Matcher
# ---------------------------------------------------------------------------

class APUMatcher:
    """Resolve a QuantityTakeoff to an APUBreakdown in the constructor PricingStore.

    Basic usage::

        matcher = APUMatcher(pricing_store)
        apu = matcher.match(takeoff)        # APUBreakdown | None
        results = matcher.match_batch(takeoffs)

    Worked examples (each requires the GEBSA constructor Excel). See
    ``tests/test_apu_matcher_rules.py`` for executable versions; the table
    below documents the expected keyword-match outcomes:

    ===========================  ============================  =================================
    Takeoff (item_type, inputs)  Expected APU                  Why
    ===========================  ============================  =================================
    column 0.30x0.20             ``6.01 COLUMNAS C1``          section verbatim in description
    column 0.40x0.20             ``6.02 COLUMNAS C2``          section verbatim
    column 0.20x0.20 amarre      ``6.03 COLUMNAS DE AMARRE``   section + ``column_type=amarre``
    beam   0.30x0.40 amarre      ``8.01 Viga de Amarre 30x40`` 30x40 + beam_type=amarre
    beam   0.20x0.40 enrase 8"   ``8.05 Vigas De Enrase 8" ``  20x40 + ``beam_type=enrase``
    beam   0.20x0.20 dintel      ``8.03 DINTELES VD 20x20``    ``dintel`` keyword + 20
    wall   8" rebar 3/8@0.40     ``10.04 BLOQUES DE 8"``       thickness + rebar gauge & spacing
    wall   12" rebar 3/8@0.40    ``10.01 BLOQUES DE 12"``      thickness + rebar
    slab   0.12 plana            ``9.01 LOSAS PLANA H=0.12``   slab_type + 0.12
    slab   0.12 inclinada        ``9.03 LOSAS DE TECHO INCL.`` slab_type=inclinada
    render interior              ``11.03 PAÑETE INTERIOR``     location=interior
    render exterior              ``11.04 PAÑETE EXTERIORES``   location=exterior
    ===========================  ============================  =================================
    """

    def __init__(
        self,
        pricing_store: PricingStore,
        *,
        construcosto_snapshot: Any | None = None,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        cache_dir: str | Path | None = _DEFAULT_CACHE_DIR,
        log_path: str | Path | None = _DEFAULT_LOG_PATH,
    ):
        self.store = pricing_store
        self.construcosto_snapshot = construcosto_snapshot
        self.embedding_model = embedding_model
        self._cache_dir = Path(cache_dir) if cache_dir else None

        # Lazy-loaded artefacts (built on first embedding call).
        self._apu_vectors: np.ndarray | None = None
        self._apu_order: list[APUBreakdown] = []   # row i in _apu_vectors -> apu

        # Pre-tokenise APUs once.
        self._apu_index: list[tuple[APUBreakdown, str, set[str]]] = []
        for apu in pricing_store.apus.values():
            desc_norm = _norm(apu.description)
            tokens = {t for t in desc_norm.split() if len(t) > 1}
            self._apu_index.append((apu, desc_norm, tokens))

        # Diagnostics: append-only file log of every match attempt + per-batch
        # summary blocks. Cumulative counters so multi-discipline runs aggregate.
        self._log_path = Path(log_path) if log_path else None
        self._stats: dict[str, int] = {
            "total": 0, "keyword": 0, "embedding": 0, "construcosto": 0, "none": 0,
        }
        if self._log_path is not None:
            try:
                self._log_path.parent.mkdir(parents=True, exist_ok=True)
                from datetime import datetime
                with self._log_path.open("a", encoding="utf-8") as fh:
                    fh.write(
                        f"\n===== APUMatcher session opened "
                        f"{datetime.now().isoformat(timespec='seconds')} | "
                        f"apus={len(self._apu_index)} =====\n"
                    )
            except Exception:
                logger.warning("Cannot open APU match log %s", self._log_path, exc_info=True)
                self._log_path = None

    # Back-compat property kept for callers that probed truthiness of the old
    # `self.embeddings` slot.
    @property
    def embeddings(self) -> Any | None:
        return self._apu_vectors

    @embeddings.setter
    def embeddings(self, value: Any | None) -> None:
        self._apu_vectors = value

    # ------------------------------------------------------------------
    # Diagnostic logging
    # ------------------------------------------------------------------

    def _takeoff_label(self, takeoff: QuantityTakeoff) -> str:
        """One-line, audit-friendly description of a takeoff."""
        inputs_blob = ", ".join(
            f"{k}={v}" for k, v in (takeoff.inputs or {}).items() if v is not None
        )
        return (
            f"{takeoff.item_key} | {takeoff.item_type} | "
            f"{takeoff.quantity} {takeoff.unit} | {{{inputs_blob}}}"
        )

    def _record(self, takeoff: QuantityTakeoff, strategy: str, apu: APUBreakdown | None) -> None:
        """Update counters and append a line to the match log."""
        self._stats["total"] += 1
        if apu is not None:
            self._stats[strategy] = self._stats.get(strategy, 0) + 1
        else:
            self._stats["none"] += 1

        line = (
            f"[{strategy:9}] {self._takeoff_label(takeoff)} -> "
            + (f"{apu.code} {apu.description[:80]}" if apu else "NO MATCH")
        )
        logger.debug(line)
        if self._log_path is not None:
            try:
                with self._log_path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except Exception:
                logger.warning("APU match log write failed", exc_info=True)

    def write_summary(self, *, label: str = "") -> dict[str, int]:
        """Flush a summary block of cumulative counters to the log.

        Returns the stats snapshot so callers can also surface it elsewhere
        (Excel report, run summary, etc.).
        """
        s = dict(self._stats)
        total = s.get("total", 0)
        matched = s.get("keyword", 0) + s.get("embedding", 0)
        block = [
            "----- APUMatcher summary" + (f" [{label}]" if label else "") + " -----",
            f"  total takeoffs evaluated: {total}",
            f"  matched by keywords:      {s.get('keyword', 0)}",
            f"  matched by embeddings:    {s.get('embedding', 0)}",
            f"  matched by ConstruCosto:  {s.get('construcosto', 0)}",
            f"  no match (BC3 fallback):  {s.get('none', 0)}",
            f"  hit rate:                 {(matched / total * 100.0) if total else 0.0:.1f}%",
        ]
        text = "\n".join(block) + "\n"
        logger.info("APUMatcher %s", " | ".join(block[1:]))
        if self._log_path is not None:
            try:
                with self._log_path.open("a", encoding="utf-8") as fh:
                    fh.write(text)
            except Exception:
                logger.warning("APU match summary write failed", exc_info=True)
        return s

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def match(self, takeoff: QuantityTakeoff) -> APUBreakdown | None:
        """Return the best APUBreakdown for *takeoff*, or None to fall back."""
        rule = self._select_rule(takeoff)

        apu = self._keyword_match(takeoff, rule)
        if apu is not None:
            self._record(takeoff, "keyword", apu)
            return apu

        apu = self._embedding_match(takeoff, rule)
        if apu is not None:
            self._record(takeoff, "embedding", apu)
            return apu

        apu = self._construcosto_match(takeoff)
        if apu is not None:
            self._record(takeoff, "construcosto", apu)
            return apu

        self._record(takeoff, "none", None)
        return None

    def match_from_inputs(
        self,
        inputs: Mapping[str, Any],
        item_type: str,
        *,
        unit: str = "",
        item_key: str = "_probe_",
    ) -> APUBreakdown | None:
        """Match without a full ``QuantityTakeoff`` object — used by replay scripts
        that work directly off ``budget_output.json`` lines.
        """
        probe = QuantityTakeoff(
            item_key=item_key,
            item_type=item_type,
            unit=unit,
            quantity=0.0,
            formula="",
            inputs=dict(inputs or {}),
        )
        return self.match(probe)

    def match_batch(
        self,
        takeoffs: list[QuantityTakeoff],
    ) -> dict[str, APUBreakdown | None]:
        """Match many takeoffs at once with one shared embedding call.

        Step 1 (keyword) runs synchronously. Takeoffs that fall through are
        embedded together in a single OpenAI call (chunked at 128), keeping
        API cost ~O(1) for the batch. After the batch a summary block with
        cumulative counters is appended to the match log.
        """
        results: dict[str, APUBreakdown | None] = {}
        pending: list[QuantityTakeoff] = []

        for t in takeoffs:
            rule = self._select_rule(t)
            apu = self._keyword_match(t, rule)
            if apu is not None:
                self._record(t, "keyword", apu)
                results[t.item_key] = apu
            else:
                pending.append(t)

        if pending:
            for t, apu in zip(pending, self._embedding_match_many(pending)):
                if apu is not None:
                    results[t.item_key] = apu
                    self._record(t, "embedding", apu)
                else:
                    # Fallback to ConstruCosto if no embedding match
                    c_apu = self._construcosto_match(t)
                    if c_apu is not None:
                        results[t.item_key] = c_apu
                        self._record(t, "construcosto", c_apu)
                    else:
                        results[t.item_key] = None
                        self._record(t, "none", None)

        self.write_summary(label=f"batch n={len(takeoffs)}")
        return results

    # ------------------------------------------------------------------
    # Step 0: rule selection
    # ------------------------------------------------------------------

    def _select_rule(self, takeoff: QuantityTakeoff) -> _ElementRule | None:
        haystack = _norm(
            " ".join(
                str(p) for p in (
                    takeoff.item_type or "",
                    takeoff.item_key or "",
                    " ".join(str(v) for v in (takeoff.inputs or {}).values() if v is not None),
                )
            )
        )
        for rule in _ELEMENT_RULES:
            if any(kw in haystack for kw in rule.takeoff_keywords):
                return rule
        return None

    # ------------------------------------------------------------------
    # Step 1: keyword match
    # ------------------------------------------------------------------

    def _keyword_match(
        self,
        takeoff: QuantityTakeoff,
        rule: _ElementRule | None,
    ) -> APUBreakdown | None:
        if rule is None:
            return None

        # Candidate APUs whose description contains the element keyword.
        candidates = [
            (apu, desc, toks)
            for apu, desc, toks in self._apu_index
            if any(kw in desc for kw in rule.apu_keywords)
        ]
        if not candidates:
            return None

        # Build the takeoff signature from declared input dimensions/qualifiers.
        dim_sig, qual_sig = _signature_from_inputs(
            takeoff.inputs, rule.dimension_fields, rule.qualifier_fields,
        )
        unit_norm = _norm(takeoff.unit)

        best: tuple[float, APUBreakdown] | None = None
        for apu, desc, _toks in candidates:
            score = self._score_keyword(
                apu_desc=desc,
                apu_unit=_norm(apu.unit),
                takeoff_unit=unit_norm,
                dim_sig=dim_sig,
                qual_sig=qual_sig,
            )
            if score <= 0:
                continue
            if best is None or score > best[0]:
                best = (score, apu)

        if best is None:
            return None
        score, apu = best
        logger.debug(
            "keyword match [%s] -> %s (score=%.2f) for takeoff %s",
            rule.name, apu.code, score, takeoff.item_key,
        )
        return apu

    @staticmethod
    def _score_keyword(
        *,
        apu_desc: str,
        apu_unit: str,
        takeoff_unit: str,
        dim_sig: set[str],
        qual_sig: set[str],
    ) -> float:
        """Cheap interpretable score.

        * +1 base for being an element-type candidate.
        * +1 per dimension token that appears verbatim in the APU description.
        * +3 per qualifier token (beam_type, slab_type, location, rebar) — these
          discriminate sub-classes ('amarre' vs 'enrase' vs 'dintel') and
          must outweigh accidental section overlap (e.g. 0.20 appearing
          inside an unrelated APU's '@ 0.20m' rebar spacing).
        * +0.5 if units agree.

        Returns 0 when neither dimensions nor qualifiers are declared —
        avoids returning the first arbitrary "Columna" APU for a column with
        no section info.
        """
        score = 1.0
        for token in dim_sig:
            if token and token in apu_desc:
                score += 1.0
        for token in qual_sig:
            if token and token in apu_desc:
                score += 3.0
        if takeoff_unit and apu_unit and takeoff_unit == apu_unit:
            score += 0.5

        if not dim_sig and not qual_sig:
            return 0.0
        return score

    # ------------------------------------------------------------------
    # Step 2: embedding match  -- placeholder for Day 7
    # ------------------------------------------------------------------

    def _embedding_match(
        self,
        takeoff: QuantityTakeoff,
        rule: _ElementRule | None,
    ) -> APUBreakdown | None:
        """Single-takeoff embedding path. Lazy-builds the APU index on first call."""
        result = self._embedding_match_many([takeoff])
        return result[0] if result else None

    # ------------------------------------------------------------------
    # Step 3: ConstruCosto fallback
    # ------------------------------------------------------------------

    def _construcosto_match(self, takeoff: QuantityTakeoff) -> APUBreakdown | None:
        if self.construcosto_snapshot is None:
            return None
        
        from budget.chapter_rules import build_budget_summary
        from pricing.construcosto_loader import find_best_price
        
        summary_s = build_budget_summary(takeoff)
        unit_s = takeoff.unit

        for sources, label in (
            (frozenset({"analisis"}), "ConstruCosto APU Punta Cana"),
            (frozenset({"materiales"}), "ConstruCosto Material Punta Cana"),
            (frozenset({"equipos"}), "ConstruCosto Equipo Punta Cana"),
            (frozenset({"mano_obra"}), "ConstruCosto Mano de obra Punta Cana"),
        ):
            match = find_best_price(
                self.construcosto_snapshot,
                summary_s,
                unit_s,
                allowed_sources=sources,
            )
            if match is not None and match.unit_price and match.unit_price > 0:
                return APUBreakdown(
                    code=match.entry.code,
                    description=match.entry.description,
                    unit=match.entry.unit,
                    unit_price_total=match.unit_price,
                    category=match.entry.category,
                    components=[],
                    source=label,
                )
        return None

    # ------------------------------------------------------------------
    # Embedding internals
    # ------------------------------------------------------------------

    def _apu_fingerprint(self) -> str:
        payload = json.dumps(
            [
                {"code": a.code, "desc": a.description, "unit": a.unit}
                for a, _, _ in self._apu_index
            ],
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _cache_paths(self) -> tuple[Path, Path] | None:
        if self._cache_dir is None:
            return None
        safe_model = self.embedding_model.replace("/", "_")
        base = self._cache_dir / f"apu_{self._apu_fingerprint()}_{safe_model}"
        return base.with_suffix(".npz"), base.with_suffix(".json")

    def _ensure_apu_vectors(self) -> bool:
        """Build (or load) the APU embedding matrix. Returns False on failure."""
        if self._apu_vectors is not None and self._apu_order:
            return True
        if not self._apu_index:
            return False

        cache = self._cache_paths()
        if cache is not None:
            npz_path, json_path = cache
            if npz_path.exists() and json_path.exists():
                try:
                    vectors = np.load(npz_path)["vectors"].astype(np.float32)
                    payload = json.loads(json_path.read_text(encoding="utf-8"))
                    codes = payload.get("codes", [])
                    by_code = {a.code: a for a, _, _ in self._apu_index}
                    order = [by_code[c] for c in codes if c in by_code]
                    if len(order) == vectors.shape[0]:
                        self._apu_vectors = vectors
                        self._apu_order = order
                        logger.info("APU embeddings loaded from cache: %s", npz_path)
                        return True
                except Exception:
                    logger.warning("APU embedding cache read failed; rebuilding", exc_info=True)

        try:
            embedder = _default_embedder(self.embedding_model)
        except Exception:
            logger.warning("No embedder available; embedding match disabled", exc_info=True)
            return False

        texts: list[str] = []
        order: list[APUBreakdown] = []
        for apu, _desc, _toks in self._apu_index:
            order.append(apu)
            # Pack description + unit + category so unit/context tilt the cosine.
            texts.append(
                f"{apu.description} | unidad {apu.unit} | {apu.category}".strip()
            )

        try:
            chunks: list[np.ndarray] = []
            for start in range(0, len(texts), _EMBED_CHUNK_SIZE):
                chunk = texts[start : start + _EMBED_CHUNK_SIZE]
                chunks.append(embedder(chunk).astype(np.float32))
            vectors = np.vstack(chunks)
        except Exception:
            logger.warning("APU embedding build failed", exc_info=True)
            return False

        vectors = np.vstack([_normalize_vector(vectors[i]) for i in range(vectors.shape[0])])
        self._apu_vectors = vectors
        self._apu_order = order

        if cache is not None:
            try:
                npz_path, json_path = cache
                npz_path.parent.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(npz_path, vectors=vectors)
                json_path.write_text(
                    json.dumps(
                        {
                            "model": self.embedding_model,
                            "codes": [a.code for a in order],
                            "threshold": _EMBEDDING_THRESHOLD,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                logger.info("APU embeddings cached at: %s", npz_path)
            except Exception:
                logger.warning("APU embedding cache write failed", exc_info=True)

        return True

    def _embed_query_texts(self, texts: list[str]) -> np.ndarray | None:
        try:
            embedder = _default_embedder(self.embedding_model)
        except Exception:
            logger.warning("No embedder available for query", exc_info=True)
            return None
        chunks: list[np.ndarray] = []
        try:
            for start in range(0, len(texts), _EMBED_CHUNK_SIZE):
                chunk = texts[start : start + _EMBED_CHUNK_SIZE]
                chunks.append(embedder(chunk).astype(np.float32))
        except Exception:
            logger.warning("Query embedding failed", exc_info=True)
            return None
        q = np.vstack(chunks)
        q = np.vstack([_normalize_vector(q[i]) for i in range(q.shape[0])])
        return q

    def _embedding_match_many(
        self,
        takeoffs: list[QuantityTakeoff],
    ) -> list[APUBreakdown | None]:
        """Embed a batch of takeoffs in one call and return best APU per takeoff."""
        if not takeoffs:
            return []
        if not self._ensure_apu_vectors():
            return [None] * len(takeoffs)

        texts = [build_query_from_takeoff(t) for t in takeoffs]
        q = self._embed_query_texts(texts)
        if q is None:
            return [None] * len(takeoffs)

        # cosine = APU_vectors @ q.T (both are L2-normalised)
        scores = self._apu_vectors @ q.T   # shape: (n_apus, n_queries)
        out: list[APUBreakdown | None] = []
        for col in range(scores.shape[1]):
            col_scores = scores[:, col]
            best_idx = int(np.argmax(col_scores))
            best_score = float(col_scores[best_idx])
            if best_score >= _EMBEDDING_THRESHOLD:
                apu = self._apu_order[best_idx]
                logger.debug(
                    "embedding match -> %s (score=%.3f) for takeoff %s",
                    apu.code, best_score, takeoffs[col].item_key,
                )
                out.append(apu)
            else:
                logger.debug(
                    "embedding miss best=%.3f < %.2f for takeoff %s",
                    best_score, _EMBEDDING_THRESHOLD, takeoffs[col].item_key,
                )
                out.append(None)
        return out
