from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class CoordinateMapper:
    scale: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0
    invert_y: bool = False
    rotation_degrees: float = 0.0
    unit_factor: float = 1.0

    def is_identity(self) -> bool:
        return (
            self.scale == 1.0
            and self.offset_x == 0.0
            and self.offset_y == 0.0
            and self.offset_z == 0.0
            and not self.invert_y
            and self.rotation_degrees == 0.0
            and self.unit_factor == 1.0
        )

    def map_point(self, x: float, y: float, z: float = 0.0) -> dict[str, float]:
        nx = float(x) * self.unit_factor * self.scale
        ny = float(y) * self.unit_factor * self.scale
        nz = float(z) * self.unit_factor * self.scale
        if self.invert_y:
            ny = -ny

        angle = math.radians(self.rotation_degrees)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        rx = nx * cos_a - ny * sin_a
        ry = nx * sin_a + ny * cos_a
        return {
            "x": rx + self.offset_x,
            "y": ry + self.offset_y,
            "z": nz + self.offset_z,
        }

    def map_bbox(self, bbox: Mapping[str, float]) -> dict[str, float]:
        min_z = float(bbox.get("min_z", 0.0))
        max_z = float(bbox.get("max_z", min_z))
        corners = [
            self.map_point(float(bbox["min_x"]), float(bbox["min_y"]), min_z),
            self.map_point(float(bbox["min_x"]), float(bbox["max_y"]), min_z),
            self.map_point(float(bbox["max_x"]), float(bbox["min_y"]), max_z),
            self.map_point(float(bbox["max_x"]), float(bbox["max_y"]), max_z),
        ]
        xs = [p["x"] for p in corners]
        ys = [p["y"] for p in corners]
        zs = [p["z"] for p in corners]
        return {
            "min_x": min(xs),
            "min_y": min(ys),
            "min_z": min(zs),
            "max_x": max(xs),
            "max_y": max(ys),
            "max_z": max(zs),
        }
