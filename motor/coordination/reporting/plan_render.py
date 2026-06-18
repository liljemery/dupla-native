"""Self-render of the cleaned ARQ modelspace + clash bbox overlays (matplotlib).

Used when no APS derivative (URN) is available for the discipline. The plan is
the ezdxf-derived bounding-box footprint of the cleaned main cluster (meters,
identity/reference frame), so overlays sit on the real element extents with no
cross-frame transform -- just model -> image scaling handled by axis limits.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from coordination.core.intra_clash import Element, IntraClash, IntraIncident  # noqa: E402

_CONTEXT_FACE = "#EAECEF"
_CONTEXT_EDGE = "#B8BfC7"
_HL_A = "#1E88E5"
_HL_B = "#8E24AA"
_OVERLAP = "#E53935"
_SEVERITY_COLOR = {"critical": "#DC2626", "major": "#D97706", "minor": "#2563EB"}


def _rect(bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = bounds
    return minx, miny, maxx - minx, maxy - miny


def render_overview(
    elements: list[Element],
    incidents: list[IntraIncident],
    out_path: str | Path,
    *,
    title: str,
    dpi: int = 150,
) -> str:
    """Whole-floor plan with every clash incident marked + numbered."""

    xs = [el.bounds[0] for el in elements] + [el.bounds[2] for el in elements]
    ys = [el.bounds[1] for el in elements] + [el.bounds[3] for el in elements]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    pad = 0.03 * max(maxx - minx, maxy - miny)

    fig, ax = plt.subplots(figsize=(11, 8.5))
    for el in elements:
        x, y, w, h = _rect(el.bounds)
        ax.add_patch(Rectangle((x, y), w, h, facecolor=_CONTEXT_FACE, edgecolor=_CONTEXT_EDGE, linewidth=0.2))

    for inc in incidents:
        x, y, w, h = _rect(inc.bounds_m)
        color = _SEVERITY_COLOR.get(inc.severity, _OVERLAP)
        ax.add_patch(
            Rectangle((x - 0.6, y - 0.6), w + 1.2, h + 1.2, facecolor="none", edgecolor=color, linewidth=1.4)
        )
        num = inc.incident_id.split("-")[-1]
        ax.annotate(
            num,
            xy=(inc.centroid_m[0], inc.centroid_m[1]),
            xytext=(inc.centroid_m[0], maxy + pad * 0.5),
            ha="center",
            fontsize=7,
            color="#FFFFFF",
            bbox={"boxstyle": "circle,pad=0.2", "fc": color, "ec": "none"},
            arrowprops={"arrowstyle": "-", "color": color, "lw": 0.6},
        )

    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad, maxy + pad)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=11)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.grid(True, color="#F0F1F3", linewidth=0.5)
    fig.tight_layout()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi)
    plt.close(fig)
    return str(out)


def render_incident(
    incident: IntraIncident,
    all_elements: list[Element],
    out_path: str | Path,
    *,
    title: str,
    min_window_m: float = 6.0,
    dpi: int = 150,
) -> str:
    """Zoomed view of one incident: context bboxes + clashing pairs + overlap."""

    minx, miny, maxx, maxy = incident.bounds_m
    cx, cy = incident.centroid_m
    half = max((maxx - minx), (maxy - miny), min_window_m) * 1.6 / 2.0
    win = (cx - half, cy - half, cx + half, cy + half)

    def intersects(el: Element) -> bool:
        return not (
            el.bounds[2] < win[0] or el.bounds[0] > win[2] or el.bounds[3] < win[1] or el.bounds[1] > win[3]
        )

    rep = incident.representative
    member_handles = {h for m in incident.members for h in (m.handle_a, m.handle_b)}
    rep_handles = {rep.handle_a, rep.handle_b}

    fig, ax = plt.subplots(figsize=(7.5, 7.0))
    for el in all_elements:
        if not intersects(el):
            continue
        x, y, w, h = _rect(el.bounds)
        if el.handle in rep_handles:
            # representative pair: bold outline + a single readable label
            edge = _HL_A if el.handle == rep.handle_a else _HL_B
            ax.add_patch(Rectangle((x, y), w, h, facecolor="none", edgecolor=edge, linewidth=2.2))
            ax.annotate(
                f"{el.layer} #{el.handle}",
                xy=(el.center[0], el.bounds[3]),
                xytext=(0, 4),
                textcoords="offset points",
                fontsize=7,
                ha="center",
                va="bottom",
                color=edge,
                bbox={"boxstyle": "round,pad=0.15", "fc": "#FFFFFF", "ec": edge, "alpha": 0.85, "lw": 0.6},
            )
        elif el.handle in member_handles:
            # other members of the incident: thin outline, no label (declutter)
            ax.add_patch(Rectangle((x, y), w, h, facecolor="none", edgecolor="#F3A0A0", linewidth=0.7))
        else:
            ax.add_patch(
                Rectangle((x, y), w, h, facecolor=_CONTEXT_FACE, edgecolor=_CONTEXT_EDGE, linewidth=0.3)
            )

    # emphasize the representative overlap; draw the rest faintly
    for m in incident.members:
        x, y, w, h = _rect(m.overlap_bounds_m)
        is_rep = (m.handle_a, m.handle_b) == (rep.handle_a, rep.handle_b)
        ax.add_patch(
            Rectangle(
                (x, y),
                w,
                h,
                facecolor=_OVERLAP,
                alpha=0.55 if is_rep else 0.18,
                edgecolor=_OVERLAP,
                linewidth=1.4 if is_rep else 0.5,
            )
        )

    ax.set_xlim(win[0], win[2])
    ax.set_ylim(win[1], win[3])
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.grid(True, color="#F0F1F3", linewidth=0.5)
    fig.tight_layout()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi)
    plt.close(fig)
    return str(out)
