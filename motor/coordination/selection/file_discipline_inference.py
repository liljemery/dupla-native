"""Infer project-file discipline from CAD layers, PDF text, or path hints."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import ezdxf
except ImportError:  # ponytail: backend subprocess env may lack CAD deps
    ezdxf = None  # type: ignore[assignment]

try:
    import fitz
except ImportError:
    fitz = None  # type: ignore[assignment]

from coordination.core.models_25d import Discipline
from coordination.core.nasas_paths import discipline_from_nasas_relative_path
from coordination.extraction.aps_cache import file_cache_key, save_cached_json
from coordination.extraction.from_autodesk_properties import (
    discipline_from_autodesk_layer,
    is_nonphysical_entity,
)
from coordination.selection.level_inference import infer_level_from_text

CONFIDENCE_THRESHOLD = 0.55


def _looks_like_binary_dwg(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(8)
    except OSError:
        return False
    return head.startswith(b"AC10") or head.startswith(b"AC1")


_PDF_DISCIPLINE_KEYWORDS: tuple[tuple[Discipline, tuple[str, ...]], ...] = (
    (Discipline.MEP_ELEC, ("eléctr", "electr", "ilumin", "tablero", "circuito", "tomacorr", "luminaria")),
    (Discipline.MEP_PLUMBING, ("sanitar", "plomer", "fontaner", "hidrosanit", "drenaje", "desagüe", "desague", "agua potable")),
    (Discipline.MEP_HVAC, ("climatiz", "hvac", "aire acond", "ventilac", "ducto", "mecánic", "mecanic")),
    (Discipline.STRUC, ("estructur", "ciment", "zapata", "viga", "columna", "refuerzo", "hormigón", "hormigon")),
    (Discipline.ARCH, ("arquitect", "acabado", "mobiliar", "fachada", "alzado", "planta arq")),
)


@dataclass(frozen=True)
class DisciplineInferenceResult:
    discipline: Discipline | None
    method: str  # ezdxf_layers | aps_layers | pdf_text | path_hint | inconclusive
    confidence: float
    layer_histogram: dict[str, int] | None = None
    dominant_layers: tuple[str, ...] = ()
    entities_sampled: int = 0
    geometry_quality: str | None = None
    level_hint: dict[str, str] | None = None
    pdf_text_snippet_chars: int = 0
    pdf_text_snippet_sha256: str | None = None
    extraction_diagnostics: dict[str, Any] | None = None
    aps_cache_key: str | None = None


def collect_layer_histogram_from_autodesk_raw(
    raw: dict[str, Any],
    *,
    max_objects: int = 2000,
) -> tuple[dict[str, int], int]:
    histogram: dict[str, int] = {}
    sampled = 0
    for view in raw.get("views") or []:
        if sampled >= max_objects:
            break
        for obj in view.get("objects") or []:
            if sampled >= max_objects:
                break
            props = obj.get("properties")
            if not isinstance(props, dict):
                continue
            general = props.get("General") or {}
            layer = str(general.get("Layer") or "")
            entity_type = str(general.get("Name ") or "").strip()
            block_name = str(
                (props.get("Misc") or {}).get("Name")
                or general.get("Block name")
                or general.get("Block Name")
                or ""
            )
            if is_nonphysical_entity(layer, entity_type, block_name):
                continue
            key = layer or "0"
            histogram[key] = histogram.get(key, 0) + 1
            sampled += 1
    return histogram, sampled


def vote_discipline_from_layer_histogram(
    histogram: dict[str, int],
) -> tuple[dict[Discipline, int], tuple[str, ...]]:
    counts: dict[Discipline, int] = {}
    for layer, weight in histogram.items():
        disc = discipline_from_autodesk_layer(layer)
        counts[disc] = counts.get(disc, 0) + weight
    dominant = tuple(layer for layer, _ in sorted(histogram.items(), key=lambda item: -item[1])[:8])
    return counts, dominant


def vote_discipline_from_autodesk_raw(
    raw: dict[str, Any],
    *,
    max_objects: int = 2000,
) -> DisciplineInferenceResult:
    histogram, sampled = collect_layer_histogram_from_autodesk_raw(raw, max_objects=max_objects)
    if not histogram:
        return DisciplineInferenceResult(
            discipline=None,
            method="inconclusive",
            confidence=0.0,
            layer_histogram={},
            entities_sampled=sampled,
        )
    counts, dominant = vote_discipline_from_layer_histogram(histogram)
    disc, confidence = _resolve_discipline_votes(counts)
    return DisciplineInferenceResult(
        discipline=disc,
        method="aps_layers" if disc else "inconclusive",
        confidence=confidence,
        layer_histogram=histogram,
        dominant_layers=dominant,
        entities_sampled=sampled,
        geometry_quality="medium" if sampled > 0 else None,
    )


def _resolve_discipline_votes(
    counts: dict[Discipline, int],
    *,
    path_hint: Discipline | None = None,
) -> tuple[Discipline | None, float]:
    if not counts:
        return None, 0.0
    total = sum(counts.values())
    if total <= 0:
        return None, 0.0
    ranked = sorted(counts.items(), key=lambda item: -item[1])
    winner, winner_count = ranked[0]
    confidence = winner_count / total
    non_arch = sum(count for disc, count in counts.items() if disc != Discipline.ARCH)
    if non_arch == 0:
        if path_hint is not None and path_hint != Discipline.ARCH:
            return path_hint, max(confidence, CONFIDENCE_THRESHOLD)
        return None, confidence
    if winner != Discipline.ARCH and confidence >= CONFIDENCE_THRESHOLD:
        return winner, confidence
    if path_hint is not None and path_hint != Discipline.ARCH:
        path_weight = counts.get(path_hint, 0) / total
        if path_weight >= 0.2 or confidence < CONFIDENCE_THRESHOLD:
            return path_hint, max(path_weight, confidence, CONFIDENCE_THRESHOLD)
    if winner != Discipline.ARCH and confidence >= 0.4:
        return winner, confidence
    return None, confidence


_EXPLICIT_FILENAME_PATTERNS: tuple[tuple[Discipline, re.Pattern[str]], ...] = (
    (Discipline.MEP_ELEC, re.compile(r"\b(?:iee|ie|elec|el)[-_ .]?\d|\belect", re.I)),
    (Discipline.MEP_PLUMBING, re.compile(r"\b(?:ihs|is|ip|san|plo)[-_ .]?\d", re.I)),
    (Discipline.MEP_HVAC, re.compile(r"\b(?:im|mec)[-_ .]?\d", re.I)),
    (Discipline.STRUC, re.compile(r"\b(?:est|es)[-_ .]?\d", re.I)),
    (Discipline.ARCH, re.compile(r"\barq\b", re.I)),
)


def _explicit_filename_discipline(combined: str) -> Discipline | None:
    """Explicit sheet codes / keywords in the file name (including ARQ)."""
    for disc, pattern in _EXPLICIT_FILENAME_PATTERNS:
        if pattern.search(combined):
            return disc
    lowered = combined.lower()
    for disc, keywords in _PDF_DISCIPLINE_KEYWORDS:
        if any(kw in lowered for kw in keywords):
            return disc
    return None


def _path_hint_discipline(path: Path, rel_posix: str | None) -> Discipline | None:
    parts: list[str] = []
    if rel_posix:
        parts.append(rel_posix.replace("\\", "/"))
    parts.append(path.name)
    combined = "/".join(parts)
    explicit = _explicit_filename_discipline(combined)
    if explicit is not None:
        return explicit
    hinted = discipline_from_nasas_relative_path(combined.lower())
    if hinted == Discipline.ARCH:
        return None
    return hinted


def _vote_discipline_from_pdf_text(text: str) -> tuple[Discipline | None, float]:
    lowered = text.lower()
    if not lowered.strip():
        return None, 0.0
    scores: dict[Discipline, int] = {}
    for disc, keywords in _PDF_DISCIPLINE_KEYWORDS:
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits:
            scores[disc] = hits
    if not scores:
        return None, 0.0
    ranked = sorted(scores.items(), key=lambda item: -item[1])
    winner, hits = ranked[0]
    total_hits = sum(scores.values())
    confidence = hits / max(total_hits, 1)
    if winner == Discipline.ARCH:
        return None, confidence
    if confidence >= CONFIDENCE_THRESHOLD or hits >= 3:
        return winner, max(confidence, CONFIDENCE_THRESHOLD)
    return None, confidence


def _extract_pdf_text(path: Path, *, max_chars: int = 8000) -> str:
    if fitz is None:
        return ""
    try:
        doc = fitz.open(path)
    except Exception:
        return ""
    chunks: list[str] = []
    try:
        for page in doc:
            chunks.append(page.get_text("text") or "")
            if sum(len(c) for c in chunks) >= max_chars:
                break
    finally:
        doc.close()
    return "\n".join(chunks)[:max_chars]


def _collect_ezdxf_layer_histogram(path: Path, *, max_entities: int = 2000) -> tuple[dict[str, int], int]:
    if ezdxf is None:
        return {}, 0
    histogram: dict[str, int] = {}
    sampled = 0
    try:
        doc = ezdxf.readfile(str(path))
    except Exception:
        return {}, 0
    for entity in doc.modelspace():
        if sampled >= max_entities:
            break
        layer = str(getattr(entity.dxf, "layer", "") or "0")
        histogram[layer] = histogram.get(layer, 0) + 1
        sampled += 1
    return histogram, sampled


def _infer_from_ezdxf(path: Path, path_hint: Discipline | None) -> DisciplineInferenceResult | None:
    if _looks_like_binary_dwg(path):
        return None
    histogram, sampled = _collect_ezdxf_layer_histogram(path)
    if not histogram:
        return None
    counts, dominant = vote_discipline_from_layer_histogram(histogram)
    disc, confidence = _resolve_discipline_votes(counts, path_hint=path_hint)
    return DisciplineInferenceResult(
        discipline=disc,
        method="ezdxf_layers" if disc else "inconclusive",
        confidence=confidence,
        layer_histogram=histogram,
        dominant_layers=dominant,
        entities_sampled=sampled,
        geometry_quality="high",
    )


def _infer_from_pdf(path: Path, path_hint: Discipline | None, cache_root: Path | None) -> DisciplineInferenceResult:
    import hashlib

    text = _extract_pdf_text(path)
    disc, confidence = _vote_discipline_from_pdf_text(text)
    if disc is None and path_hint is not None:
        disc = path_hint
        confidence = max(confidence, CONFIDENCE_THRESHOLD)
        method = "path_hint"
    else:
        method = "pdf_text" if disc else "inconclusive"
    level = infer_level_from_text(path.stem, doc=None, default_level_id="GENERAL")
    snippet_sha = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None
    cache_key = file_cache_key(path)
    if cache_root is not None and text:
        save_cached_json(cache_root, key=cache_key, suffix="pdf_snippet", payload={"text": text})
    return DisciplineInferenceResult(
        discipline=disc,
        method=method,
        confidence=confidence,
        entities_sampled=len(text),
        pdf_text_snippet_chars=len(text),
        pdf_text_snippet_sha256=snippet_sha,
        aps_cache_key=cache_key,
        level_hint={"level_id": level.level_id, "source": level.source},
    )


def infer_discipline_from_file(
    path: Path,
    *,
    rel_posix: str | None = None,
    cache_root: Path | None = None,
    aps_raw: dict[str, Any] | None = None,
) -> DisciplineInferenceResult:
    path = path.resolve()
    path_hint = _path_hint_discipline(path, rel_posix)
    ext = path.suffix.lower()

    if ext == ".pdf":
        return _infer_from_pdf(path, path_hint, cache_root)

    if ext in (".dwg", ".dxf"):
        ezdxf_result = _infer_from_ezdxf(path, path_hint)
        if ezdxf_result is not None and ezdxf_result.discipline is not None:
            ezdxf_result = DisciplineInferenceResult(
                discipline=ezdxf_result.discipline,
                method=ezdxf_result.method,
                confidence=ezdxf_result.confidence,
                layer_histogram=ezdxf_result.layer_histogram,
                dominant_layers=ezdxf_result.dominant_layers,
                entities_sampled=ezdxf_result.entities_sampled,
                geometry_quality=ezdxf_result.geometry_quality,
                aps_cache_key=file_cache_key(path),
            )
            return ezdxf_result
        if aps_raw is not None:
            aps_result = vote_discipline_from_autodesk_raw(aps_raw)
            counts, _ = vote_discipline_from_layer_histogram(aps_result.layer_histogram or {})
            disc, confidence = _resolve_discipline_votes(counts, path_hint=path_hint)
            method = "aps_layers"
            if disc is None and path_hint is not None:
                disc = path_hint
                confidence = max(confidence, CONFIDENCE_THRESHOLD)
                method = "path_hint"
            elif disc is None:
                method = "inconclusive"
            return DisciplineInferenceResult(
                discipline=disc,
                method=method,
                confidence=confidence,
                layer_histogram=aps_result.layer_histogram,
                dominant_layers=aps_result.dominant_layers,
                entities_sampled=aps_result.entities_sampled,
                geometry_quality=aps_result.geometry_quality,
                aps_cache_key=file_cache_key(path),
                extraction_diagnostics=aps_result.extraction_diagnostics,
            )

    if path_hint is not None:
        return DisciplineInferenceResult(
            discipline=path_hint,
            method="path_hint",
            confidence=CONFIDENCE_THRESHOLD,
        )
    return DisciplineInferenceResult(discipline=None, method="inconclusive", confidence=0.0)


def motor_discipline_to_bucket_value(discipline: Discipline | None) -> str | None:
    if discipline is None:
        return None
    mapping = {
        Discipline.ARCH: "arquitectura",
        Discipline.STRUC: "estructura",
        Discipline.MEP_HVAC: "mecanica",
        Discipline.MEP_ELEC: "electrica",
        Discipline.MEP_PLUMBING: "plomeria",
    }
    return mapping.get(discipline)


if __name__ == "__main__":
    assert _resolve_discipline_votes({Discipline.MEP_ELEC: 80, Discipline.ARCH: 20})[0] == Discipline.MEP_ELEC
    assert _resolve_discipline_votes({Discipline.ARCH: 100})[0] is None
    assert _vote_discipline_from_pdf_text("instalación eléctrica tablero circuito")[0] == Discipline.MEP_ELEC
    assert _path_hint_discipline(Path("LAS NASAS Plans ARQ Nov 21.dwg"), None) == Discipline.ARCH
    print("file_discipline_inference self-check ok")
