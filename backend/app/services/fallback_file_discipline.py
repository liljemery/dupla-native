"""Lightweight discipline inference when motor is unavailable (Docker/dev fallback)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.domain.file_discipline import FileDiscipline, guess_discipline_from_filename
from app.services.motor_discipline_types import MotorDisciplineInference
from app.services.pliego_ga_fo_file_classifier import extract_pdf_text_snippet

_PDF_KEYWORDS: tuple[tuple[FileDiscipline, tuple[str, ...]], ...] = (
    (FileDiscipline.ELECTRICA, ("eléctr", "electr", "ilumin", "tablero", "circuito")),
    (FileDiscipline.PLOMERIA, ("sanitar", "plomer", "fontaner", "drenaje", "agua potable")),
    (FileDiscipline.MECANICA, ("climatiz", "hvac", "aire acond", "ventilac", "mecánic")),
    (FileDiscipline.ESTRUCTURA, ("estructur", "ciment", "viga", "columna", "refuerzo")),
    (FileDiscipline.ARQUITECTURA, ("arquitect", "acabado", "fachada", "alzado")),
)


def _vote_pdf_text(text: str) -> tuple[FileDiscipline | None, float]:
    lowered = text.lower()
    if not lowered.strip():
        return None, 0.0
    scores: dict[FileDiscipline, int] = {}
    for disc, keywords in _PDF_KEYWORDS:
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits:
            scores[disc] = hits
    if not scores:
        return None, 0.0
    winner, hits = max(scores.items(), key=lambda item: item[1])
    if winner == FileDiscipline.ARQUITECTURA:
        return None, hits / max(sum(scores.values()), 1)
    confidence = hits / max(sum(scores.values()), 1)
    if confidence >= 0.55 or hits >= 2:
        return winner, max(confidence, 0.55)
    return None, confidence


def infer_discipline_fallback(
    path: Path,
    *,
    original_name: str,
    rel_posix: str | None,
) -> MotorDisciplineInference:
    classified_at = datetime.now(timezone.utc).isoformat()
    hint_parts = [p for p in (rel_posix, original_name) if p]
    combined = "/".join(hint_parts).lower()
    disc = guess_discipline_from_filename(original_name)
    method = "path_hint"
    confidence = 0.55 if disc else 0.0

    pdf_chars = 0
    if path.suffix.lower() == ".pdf":
        text = extract_pdf_text_snippet(path)
        pdf_chars = len(text or "")
        pdf_disc, pdf_conf = _vote_pdf_text(text or "")
        if pdf_disc is not None:
            disc = pdf_disc
            method = "pdf_text"
            confidence = pdf_conf
        elif disc is None and any(k in combined for k in ("elect", "sanit", "estruct", "mecan", "arquitect")):
            disc = guess_discipline_from_filename(combined.replace("/", "-"))
            if disc:
                method = "path_hint"
                confidence = 0.55

    snapshot = {
        "classified_at": classified_at,
        "discipline_method": method,
        "confidence": confidence,
        "pdf_text_snippet_chars": pdf_chars,
        "extraction_diagnostics": {"result": "backend_fallback", "motor": "unavailable"},
    }
    return MotorDisciplineInference(
        discipline=disc,
        method=method,
        confidence=confidence,
        snapshot=snapshot,
    )
