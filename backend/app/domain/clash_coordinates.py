"""Coordinate labeling for clash workflow UI and exports."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Point2D(BaseModel):
    x_mm: float
    y_mm: float


class ClashLocation(BaseModel):
    unit: str = "mm"
    centroid: Point2D
    bounds_min: Point2D
    bounds_max: Point2D
    alignment_offset_mm: tuple[float, float] | None = Field(default=None)

    @property
    def world_centroid(self) -> Point2D:
        if not self.alignment_offset_mm:
            return self.centroid
        dx, dy = self.alignment_offset_mm
        return Point2D(x_mm=self.centroid.x_mm - dx, y_mm=self.centroid.y_mm - dy)

    @property
    def world_bounds(self) -> tuple[Point2D, Point2D]:
        if not self.alignment_offset_mm:
            return self.bounds_min, self.bounds_max
        dx, dy = self.alignment_offset_mm
        return (
            Point2D(x_mm=self.bounds_min.x_mm - dx, y_mm=self.bounds_min.y_mm - dy),
            Point2D(x_mm=self.bounds_max.x_mm - dx, y_mm=self.bounds_max.y_mm - dy),
        )

    def autocad_zoom_window_command(self, *, use_world: bool = True) -> str:
        if use_world:
            c = self.world_centroid
            bmin, bmax = self.world_bounds
        else:
            c = self.centroid
            bmin, bmax = self.bounds_min, self.bounds_max
        pad = max((bmax.x_mm - bmin.x_mm), (bmax.y_mm - bmin.y_mm)) * 0.15 or 500.0
        return (
            f"ZOOM W {bmin.x_mm - pad:.3f},{bmin.y_mm - pad:.3f} "
            f"{bmax.x_mm + pad:.3f},{bmax.y_mm + pad:.3f}"
        )

    def ui_payload(self) -> dict[str, Any]:
        wc = self.world_centroid
        bmin, bmax = self.world_bounds
        return {
            "unit": self.unit,
            "model_centroid": {"x": self.centroid.x_mm, "y": self.centroid.y_mm, "space": "model"},
            "world_centroid": {"x": wc.x_mm, "y": wc.y_mm, "space": "world"},
            "world_bounds": {
                "min": {"x": bmin.x_mm, "y": bmin.y_mm},
                "max": {"x": bmax.x_mm, "y": bmax.y_mm},
            },
            "alignment_offset_mm": list(self.alignment_offset_mm) if self.alignment_offset_mm else None,
            "autocad_zoom_window_command": self.autocad_zoom_window_command(),
        }


def location_from_mm(
    *,
    centroid_mm: tuple[float, float],
    bounds_mm: tuple[float, float, float, float],
    alignment_offset_mm: tuple[float, float] | None = None,
) -> ClashLocation:
    return ClashLocation(
        centroid=Point2D(x_mm=centroid_mm[0], y_mm=centroid_mm[1]),
        bounds_min=Point2D(x_mm=bounds_mm[0], y_mm=bounds_mm[1]),
        bounds_max=Point2D(x_mm=bounds_mm[2], y_mm=bounds_mm[3]),
        alignment_offset_mm=alignment_offset_mm,
    )
