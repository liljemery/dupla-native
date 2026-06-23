"""Solve DXF model-space to APS sheet-space transforms."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np

from coordination.core.frame_alignment import fit_similarity
from coordination.extraction.dxf_aps_matching import DxfApsMatchPair
from coordination.extraction.dxf_geometry import BoundsXY

DEFAULT_SHEET_THRESHOLDS = (0.02, 0.05, 0.10, 0.25, 0.50)
DEFAULT_MIN_INLIERS = 3
DEFAULT_MIN_MODEL_SPREAD = 1.0


@dataclass(frozen=True)
class DxfApsAlignmentTransform:
    status: str
    scale: float | None = None
    rotation_deg: float | None = None
    flip_y: bool = False
    translation: tuple[float, float] | None = None
    matrix: tuple[tuple[float, float], tuple[float, float]] | None = None
    rms_error_sheet: float | None = None
    max_error_sheet: float | None = None
    n_pairs: int = 0
    n_inliers: int = 0
    n_outliers: int = 0
    ransac_threshold_sheet: float | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "scale": self.scale,
            "rotation_deg": self.rotation_deg,
            "flip_y": self.flip_y,
            "translation": list(self.translation) if self.translation is not None else None,
            "matrix": [list(row) for row in self.matrix] if self.matrix is not None else None,
            "rms_error_sheet": self.rms_error_sheet,
            "max_error_sheet": self.max_error_sheet,
            "n_pairs": self.n_pairs,
            "n_inliers": self.n_inliers,
            "n_outliers": self.n_outliers,
            "ransac_threshold_sheet": self.ransac_threshold_sheet,
            "reason": self.reason,
        }


@dataclass
class DxfApsAlignmentReport:
    transform: DxfApsAlignmentTransform
    inlier_handles: list[str] = field(default_factory=list)
    outlier_handles: list[str] = field(default_factory=list)
    residuals_by_handle: dict[str, float] = field(default_factory=dict)
    view_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "view_name": self.view_name,
            "transform": self.transform.to_dict(),
            "inlier_handles": list(self.inlier_handles),
            "outlier_handles": list(self.outlier_handles),
            "residuals_by_handle": dict(self.residuals_by_handle),
        }


def _as_arrays(pairs: list[DxfApsMatchPair]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    model = np.asarray([pair.dxf.model_center for pair in pairs], dtype=float)
    sheet = np.asarray([pair.aps.sheet_center for pair in pairs], dtype=float)
    handles = [pair.handle for pair in pairs]
    return model, sheet, handles


def _model_spread_ok(model: np.ndarray, mask: np.ndarray, min_model_spread: float) -> bool:
    if int(mask.sum()) < 2:
        return False
    points = model[mask]
    return bool(np.ptp(points[:, 0]) >= min_model_spread or np.ptp(points[:, 1]) >= min_model_spread)


def _apply_matrix(points: np.ndarray, matrix: np.ndarray, translation: np.ndarray) -> np.ndarray:
    return (matrix @ points.T).T + translation


def _serializable_transform(
    final: dict[str, Any],
    *,
    n_pairs: int,
    n_inliers: int,
    n_outliers: int,
    threshold: float | None,
    residuals: np.ndarray,
) -> DxfApsAlignmentTransform:
    matrix = np.asarray(final["matrix"], dtype=float)
    translation = np.asarray(final["translation"], dtype=float)
    return DxfApsAlignmentTransform(
        status="ok",
        scale=float(final["scale"]),
        rotation_deg=float(final["rotation_deg"]),
        flip_y=bool(final["flip_y"]),
        translation=(float(translation[0]), float(translation[1])),
        matrix=((float(matrix[0, 0]), float(matrix[0, 1])), (float(matrix[1, 0]), float(matrix[1, 1]))),
        rms_error_sheet=float(np.sqrt(np.mean(residuals ** 2))),
        max_error_sheet=float(np.max(residuals)),
        n_pairs=n_pairs,
        n_inliers=n_inliers,
        n_outliers=n_outliers,
        ransac_threshold_sheet=threshold,
    )


def solve_dxf_to_aps_alignment(
    pairs: Iterable[DxfApsMatchPair],
    *,
    thresholds_sheet: tuple[float, ...] = DEFAULT_SHEET_THRESHOLDS,
    min_inliers: int = DEFAULT_MIN_INLIERS,
    min_model_spread: float = DEFAULT_MIN_MODEL_SPREAD,
    max_trials: int | None = None,
    view_name: str | None = None,
) -> DxfApsAlignmentReport:
    """Fit a robust similarity transform from DXF model centers to APS sheet centers."""
    pair_list = list(pairs)
    n = len(pair_list)
    if n < min_inliers:
        return DxfApsAlignmentReport(
            transform=DxfApsAlignmentTransform(status="insufficient", n_pairs=n, reason=f"need >= {min_inliers} pairs"),
            view_name=view_name,
        )

    model, sheet, handles = _as_arrays(pair_list)
    if not np.all(np.isfinite(model)) or not np.all(np.isfinite(sheet)):
        return DxfApsAlignmentReport(
            transform=DxfApsAlignmentTransform(status="invalid_input", n_pairs=n, reason="non-finite coordinates"),
            view_name=view_name,
        )

    rng = random.Random(42)
    best: dict[str, Any] | None = None
    trials = max_trials if max_trials is not None else min(750, max(150, n * 6))
    for _ in range(trials):
        idx = rng.sample(range(n), 2)
        for flip in (False, True):
            seed = fit_similarity(model[idx], sheet[idx], flip)
            if not seed or seed["scale"] <= 1e-8 or seed["scale"] >= 1e8:
                continue
            matrix = np.asarray(seed["matrix"], dtype=float)
            translation = np.asarray(seed["translation"], dtype=float)
            residuals = np.linalg.norm(_apply_matrix(model, matrix, translation) - sheet, axis=1)
            for threshold in thresholds_sheet:
                mask = residuals <= threshold
                count = int(mask.sum())
                if count < min_inliers:
                    continue
                if not _model_spread_ok(model, mask, min_model_spread):
                    continue
                rms = float(np.sqrt(np.mean(residuals[mask] ** 2)))
                score = (count, -rms, -float(threshold))
                if best is None or score > best["score"]:
                    best = {"score": score, "mask": mask, "threshold": float(threshold)}

    if best is None:
        mask = np.ones(n, dtype=bool)
        threshold = None
        if not _model_spread_ok(model, mask, min_model_spread):
            return DxfApsAlignmentReport(
                transform=DxfApsAlignmentTransform(
                    status="degenerate",
                    n_pairs=n,
                    reason=f"model control points spread less than {min_model_spread:g}",
                ),
                view_name=view_name,
            )
    else:
        mask = best["mask"]
        threshold = best["threshold"]

    model_i = model[mask]
    sheet_i = sheet[mask]
    candidates = [fit for fit in (fit_similarity(model_i, sheet_i, False), fit_similarity(model_i, sheet_i, True)) if fit]
    if not candidates:
        return DxfApsAlignmentReport(
            transform=DxfApsAlignmentTransform(status="degenerate", n_pairs=n, n_inliers=int(mask.sum()), reason="fit failed"),
            view_name=view_name,
        )

    final = min(candidates, key=lambda fit: float(np.sqrt(np.mean(fit["residuals"] ** 2))))
    matrix = np.asarray(final["matrix"], dtype=float)
    translation = np.asarray(final["translation"], dtype=float)
    residuals_all = np.linalg.norm(_apply_matrix(model, matrix, translation) - sheet, axis=1)
    residuals_inliers = residuals_all[mask]
    transform = _serializable_transform(
        final,
        n_pairs=n,
        n_inliers=int(mask.sum()),
        n_outliers=int(n - mask.sum()),
        threshold=threshold,
        residuals=residuals_inliers,
    )
    return DxfApsAlignmentReport(
        transform=transform,
        inlier_handles=[handle for handle, keep in zip(handles, mask) if keep],
        outlier_handles=[handle for handle, keep in zip(handles, mask) if not keep],
        residuals_by_handle={handle: float(round(residual, 8)) for handle, residual in zip(handles, residuals_all)},
        view_name=view_name,
    )


def solve_dxf_to_aps_alignment_by_view(
    pairs: Iterable[DxfApsMatchPair],
    **kwargs: Any,
) -> dict[str, DxfApsAlignmentReport]:
    grouped: dict[str, list[DxfApsMatchPair]] = {}
    for pair in pairs:
        grouped.setdefault(pair.aps.view_name, []).append(pair)
    return {
        view_name: solve_dxf_to_aps_alignment(view_pairs, view_name=view_name, **kwargs)
        for view_name, view_pairs in sorted(grouped.items())
    }


def apply_alignment_to_point(point: tuple[float, float], transform: DxfApsAlignmentTransform | dict[str, Any]) -> tuple[float, float]:
    payload = transform.to_dict() if isinstance(transform, DxfApsAlignmentTransform) else transform
    if payload.get("status") != "ok":
        raise ValueError(f"cannot apply non-ok alignment transform: {payload.get('status')}")
    matrix = np.asarray(payload["matrix"], dtype=float)
    translation = np.asarray(payload["translation"], dtype=float)
    result = _apply_matrix(np.asarray([point], dtype=float), matrix, translation)[0]
    return (float(result[0]), float(result[1]))


def apply_alignment_to_bounds(bounds: BoundsXY, transform: DxfApsAlignmentTransform | dict[str, Any]) -> BoundsXY:
    points = [
        apply_alignment_to_point((bounds[0], bounds[1]), transform),
        apply_alignment_to_point((bounds[2], bounds[1]), transform),
        apply_alignment_to_point((bounds[2], bounds[3]), transform),
        apply_alignment_to_point((bounds[0], bounds[3]), transform),
    ]
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )

