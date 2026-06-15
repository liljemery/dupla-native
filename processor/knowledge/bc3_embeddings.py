"""
In-memory semantic embeddings index for BC3 catalog search.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

import numpy as np

from core.schemas import QuantityTakeoff

logger = logging.getLogger("dupla.embeddings")

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional at runtime
    OpenAI = None  # type: ignore[assignment]


DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_CACHE_DIR = Path(__file__).parent / "cache"


@dataclass
class EmbeddingIndex:
    vectors: np.ndarray
    metadata: list[dict[str, Any]]
    model: str
    created_at: str
    cache_key: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["vectors_shape"] = list(self.vectors.shape)
        payload.pop("vectors")
        return payload


def _normalize_vector(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm == 0:
        return vector
    return vector / norm


def _build_item_text(item: dict[str, Any]) -> str:
    return " | ".join(
        [
            str(item.get("code", "")).strip(),
            str(item.get("summary", "")).strip(),
            str(item.get("long_text", "")).strip(),
            str(item.get("unit", "")).strip(),
        ]
    ).strip()


def _catalog_fingerprint(bc3_catalog: dict[str, Any]) -> str:
    # Include bc3_origin so merged multi-file catalogs invalidate cache when sources change.
    serializable = [
        {
            "code": item.get("code", ""),
            "summary": item.get("summary", ""),
            "long_text": item.get("long_text", ""),
            "unit": item.get("unit", ""),
            "price": item.get("price", 0),
            "bc3_origin": item.get("bc3_origin", ""),
        }
        for item in bc3_catalog.get("items", [])
    ]
    payload = json.dumps(serializable, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _default_embedder(model: str) -> Callable[[list[str]], np.ndarray]:
    if OpenAI is None:
        raise RuntimeError("openai package is required to build/search embeddings.")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for semantic embeddings.")
    client = OpenAI(api_key=api_key)

    def _embed_batch(texts: list[str]) -> np.ndarray:
        response = client.embeddings.create(model=model, input=texts)
        vectors = [entry.embedding for entry in response.data]
        return np.asarray(vectors, dtype=np.float32)

    return _embed_batch


def _cache_paths(cache_dir: Path, cache_key: str, model: str) -> tuple[Path, Path]:
    safe_model = model.replace("/", "_")
    prefix = f"bc3_{cache_key}_{safe_model}"
    return cache_dir / f"{prefix}.npz", cache_dir / f"{prefix}.json"


def build_bc3_embeddings(
    bc3_catalog: dict[str, Any],
    *,
    model: str = DEFAULT_EMBEDDING_MODEL,
    embed_batch_fn: Callable[[list[str]], np.ndarray] | None = None,
    cache_dir: str | Path | None = DEFAULT_CACHE_DIR,
) -> EmbeddingIndex:
    items = list(bc3_catalog.get("items", []))
    if not items:
        raise ValueError("bc3_catalog has no items to embed.")

    embedder = embed_batch_fn or _default_embedder(model)
    cache_key = _catalog_fingerprint(bc3_catalog)
    metadata = []
    texts = []
    for item in items:
        text = _build_item_text(item)
        texts.append(text)
        metadata.append(
            {
                "code": str(item.get("code", "")),
                "summary": str(item.get("summary", "")),
                "long_text": str(item.get("long_text", "")),
                "unit": str(item.get("unit", "")),
                "price": float(item.get("price") or 0.0),
                "search_text": text,
            }
        )

    vectors = embedder(texts)
    if vectors.shape[0] != len(metadata):
        raise RuntimeError("Embedding count mismatch against BC3 items.")
    vectors = vectors.astype(np.float32, copy=False)
    vectors = np.vstack([_normalize_vector(vector) for vector in vectors])

    index = EmbeddingIndex(
        vectors=vectors,
        metadata=metadata,
        model=model,
        created_at=datetime.now(timezone.utc).isoformat(),
        cache_key=cache_key,
    )

    if cache_dir is not None:
        cache_path = Path(cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        npz_path, json_path = _cache_paths(cache_path, cache_key, model)
        np.savez_compressed(npz_path, vectors=vectors)
        json_path.write_text(
            json.dumps(
                {
                    "model": index.model,
                    "created_at": index.created_at,
                    "cache_key": index.cache_key,
                    "metadata": index.metadata,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return index


def load_or_build_embeddings(
    bc3_catalog: dict[str, Any],
    *,
    model: str = DEFAULT_EMBEDDING_MODEL,
    embed_batch_fn: Callable[[list[str]], np.ndarray] | None = None,
    cache_dir: str | Path | None = DEFAULT_CACHE_DIR,
) -> EmbeddingIndex | None:
    items = list(bc3_catalog.get("items", []))
    if not items:
        return None

    cache_path = Path(cache_dir) if cache_dir is not None else None
    cache_key = _catalog_fingerprint(bc3_catalog)
    if cache_path is not None:
        cache_path.mkdir(parents=True, exist_ok=True)
        npz_path, json_path = _cache_paths(cache_path, cache_key, model)
        if npz_path.exists() and json_path.exists():
            vectors = np.load(npz_path)["vectors"].astype(np.float32)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            return EmbeddingIndex(
                vectors=vectors,
                metadata=list(payload.get("metadata", [])),
                model=str(payload.get("model", model)),
                created_at=str(payload.get("created_at", "")),
                cache_key=str(payload.get("cache_key", cache_key)),
            )

    return build_bc3_embeddings(
        bc3_catalog,
        model=model,
        embed_batch_fn=embed_batch_fn,
        cache_dir=cache_path,
    )


def batch_search_bc3(
    queries: list[str],
    index: EmbeddingIndex,
    top_k: int = 5,
    *,
    embed_batch_fn: Callable[[list[str]], np.ndarray] | None = None,
    embed_chunk_size: int = 128,
) -> list[list[dict[str, Any]]]:
    """
    Semantic search for many queries with one (or few) embedding API calls.

    Returns one result list per query (same length as ``queries``); empty strings
    yield empty lists without calling the embedder.
    """
    if not queries:
        return []
    if index.vectors.size == 0:
        return [[] for _ in queries]

    embedder = embed_batch_fn or _default_embedder(index.model)
    non_empty: list[tuple[int, str]] = [
        (i, str(q).strip()) for i, q in enumerate(queries) if q and str(q).strip()
    ]
    out: list[list[dict[str, Any]]] = [[] for _ in queries]
    if not non_empty:
        return out

    texts = [t for _, t in non_empty]
    chunks: list[np.ndarray] = []
    for start in range(0, len(texts), embed_chunk_size):
        chunk = texts[start : start + embed_chunk_size]
        chunks.append(embedder(chunk).astype(np.float32))
    q_matrix = np.vstack(chunks)
    q_matrix = np.vstack([_normalize_vector(q_matrix[i]) for i in range(q_matrix.shape[0])])
    scores = index.vectors @ q_matrix.T

    limit = min(max(top_k, 1), len(index.metadata))
    for col, (orig_idx, _) in enumerate(non_empty):
        col_scores = scores[:, col]
        ranked_indices = np.argsort(col_scores)[::-1][:limit]
        row: list[dict[str, Any]] = []
        for idx in ranked_indices:
            meta = dict(index.metadata[int(idx)])
            meta["score"] = float(col_scores[int(idx)])
            row.append(meta)
        out[orig_idx] = row
    return out


def search_bc3(
    query_text: str,
    index: EmbeddingIndex,
    top_k: int = 5,
    *,
    embed_batch_fn: Callable[[list[str]], np.ndarray] | None = None,
) -> list[dict[str, Any]]:
    if not query_text.strip():
        return []
    if index.vectors.size == 0:
        return []

    embedder = embed_batch_fn or _default_embedder(index.model)
    query_vector = embedder([query_text]).astype(np.float32)[0]
    query_vector = _normalize_vector(query_vector)
    scores = index.vectors @ query_vector

    limit = min(max(top_k, 1), len(index.metadata))
    ranked_indices = np.argsort(scores)[::-1][:limit]
    results: list[dict[str, Any]] = []
    for idx in ranked_indices:
        meta = dict(index.metadata[int(idx)])
        meta["score"] = float(scores[int(idx)])
        results.append(meta)
    return results


def build_query_from_takeoff(takeoff: QuantityTakeoff) -> str:
    specific = str(takeoff.inputs.get("takeoff_description") or "").strip()
    item_type_to_spanish = {
        "wall_finish_plaster": "panete en muros interiores",
        "door_count": "puerta de madera interior",
        "floor_finish": "piso porcelanato ceramica",
    }
    item_type_desc = item_type_to_spanish.get(takeoff.item_type, takeoff.item_type)
    trace_evidence = " ".join(takeoff.trace.evidence)
    assumptions = " ".join(takeoff.assumptions)
    formula = takeoff.formula or ""
    extra = ""
    if takeoff.item_type == "fixture_count":
        disc = str(takeoff.inputs.get("discipline") or "")
        ftype = str(takeoff.inputs.get("fixture_type") or "")
        loc = str(takeoff.inputs.get("location_hint") or "")
        raw = takeoff.inputs.get("raw")
        raw_txt = ""
        if isinstance(raw, dict):
            raw_txt = str(raw.get("id") or raw.get("type") or "")
        extra = f" disciplina {disc} tipo {ftype} ubicacion {loc} {raw_txt}".strip()
    core = (
        f"{item_type_desc} unidad {takeoff.unit} formula {formula} "
        f"supuestos {assumptions} evidencia {trace_evidence} {extra}"
    ).strip()
    return f"{specific} {core}".strip() if specific else core
