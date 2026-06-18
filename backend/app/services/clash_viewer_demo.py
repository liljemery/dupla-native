from __future__ import annotations

from app.schemas.clash_viewer import BBox3D, ClashViewerResponse, ClashViewerSummary, ViewerClash


def demo_clashes_response(
    *,
    coordinate_space: str = "world",
    severity: str | None = None,
    discipline: str | None = None,
) -> ClashViewerResponse:
    clashes = [
        _clash("CL-0001", "structure", "plumbing", "critical", "hard_2d", (1000, 1000, 1500, 1450)),
        _clash("CL-0002", "structure", "mechanical", "high", "hard_2d", (2500, 1800, 3300, 2250)),
        _clash("CL-0003", "architecture", "electrical", "medium", "soft_clearance", (4200, 900, 4700, 1350)),
        _clash("CL-0004", "architecture", "plumbing", "low", "soft_clearance", (1600, 3100, 2100, 3500)),
        _clash("CL-0005", "architecture", "electrical", "medium", "rule_based", (3600, 2900, 4100, 3350)),
    ]
    if severity:
        clashes = [c for c in clashes if c.severity == severity]
    if discipline:
        d = discipline.lower()
        clashes = [c for c in clashes if d in {c.discipline_a, c.discipline_b}]
    counts = {key: 0 for key in ["critical", "high", "medium", "low"]}
    for clash in clashes:
        counts[clash.severity] += 1
    return ClashViewerResponse(
        project_id="demo",
        coordinate_space="model" if coordinate_space == "model" else "world",
        warnings=["DEMO_MODE"],
        summary=ClashViewerSummary(total=len(clashes), **counts),
        clashes=clashes,
    )


def _clash(
    clash_id: str,
    discipline_a: str,
    discipline_b: str,
    severity: str,
    clash_type: str,
    bounds: tuple[float, float, float, float],
) -> ViewerClash:
    bbox = BBox3D(min_x=bounds[0], min_y=bounds[1], max_x=bounds[2], max_y=bounds[3])
    center = {
        "x": (bbox.min_x + bbox.max_x) / 2,
        "y": (bbox.min_y + bbox.max_y) / 2,
        "z": 0,
    }
    return ViewerClash(
        id=clash_id,
        source_clash_id=clash_id,
        job_id=None,
        project_id="demo",
        dwg_a=f"{discipline_a}.dwg",
        dwg_b=f"{discipline_b}.dwg",
        file_pair=[f"{discipline_a}.dwg", f"{discipline_b}.dwg"],
        discipline_a=discipline_a,
        discipline_b=discipline_b,
        layer_a=f"{discipline_a}-demo",
        layer_b=f"{discipline_b}-demo",
        clash_type=clash_type,
        confidence="medium",
        severity=severity,
        status="open",
        model_bbox_mm=bbox,
        world_bbox_mm=bbox,
        viewer_bbox=bbox,
        center=center,
        description=f"Demo {severity}: {discipline_a} vs {discipline_b}.",
        recommendation="Validar coordenadas y resolver en coordinación.",
    )
