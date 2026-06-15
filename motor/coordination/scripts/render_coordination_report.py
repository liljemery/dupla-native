#!/usr/bin/env python3
"""Render reusable coordination reports from an existing fast_compare output folder."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coordination.core.clash import ClashIncident
from coordination.selection.coordinate_audit import SourceAudit, render_coordinate_audit_markdown, render_hotspot_markdown
from coordination.reporting.reporting import (
    build_coordination_report_context,
    render_coordination_report_markdown,
    render_primary_incidents_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render technical coordination report from existing outputs.")
    parser.add_argument("--run-dir", type=Path, required=True, help="Folder with summary.json and related outputs.")
    parser.add_argument("--root", type=Path, default=None, help="Override project root shown in the markdown.")
    parser.add_argument("--output", type=Path, default=None, help="Output markdown path. Default: technical_coordination_report.md in run-dir.")
    parser.add_argument(
        "--refresh-supporting-md",
        action="store_true",
        help="Also refresh primary_incidents.md, coordinate_audit.md, and hotspot_incidents.md from JSON.",
    )
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    summary_payload = _load_json(run_dir / "summary.json")
    primary_payload = _load_json(run_dir / "primary_incidents.json")
    debug_payload = _load_optional_json(run_dir / "debug_candidates.json")
    hotspot_payload = _load_optional_json(run_dir / "hotspot_incidents.json")
    coordinate_audit_payload = _load_optional_json(run_dir / "coordinate_audit.json")
    pair_schedule_payload = _load_optional_json(run_dir / "pair_schedule.json")

    project_root = args.root or Path(str(summary_payload.get("nasas_root") or run_dir))
    project_name = str(primary_payload.get("project_name") or summary_payload.get("project_name") or "Proyecto")

    context = build_coordination_report_context(
        summary_payload=summary_payload,
        primary_payload=primary_payload,
        debug_payload=debug_payload,
        hotspot_payload=hotspot_payload,
        coordinate_audit_payload=coordinate_audit_payload,
        pair_schedule_payload=pair_schedule_payload,
    )
    context_path = run_dir / "coordination_report_context.json"
    context_path.write_text(json.dumps(context, indent=2, ensure_ascii=False), encoding="utf-8")

    output_path = args.output.resolve() if args.output else run_dir / "technical_coordination_report.md"
    output_path.write_text(
        render_coordination_report_markdown(
            project_name=project_name,
            root=project_root,
            summary_payload=summary_payload,
            primary_payload=primary_payload,
            debug_payload=debug_payload,
            hotspot_payload=hotspot_payload,
            coordinate_audit_payload=coordinate_audit_payload,
            pair_schedule_payload=pair_schedule_payload,
        ),
        encoding="utf-8",
    )

    if args.refresh_supporting_md:
        (run_dir / "primary_incidents.md").write_text(
            render_primary_incidents_markdown(
                project_name=project_name,
                root=project_root,
                primary_payload=primary_payload,
            ),
            encoding="utf-8",
        )
        if coordinate_audit_payload:
            audits = [SourceAudit.model_validate(item) for item in coordinate_audit_payload.get("audits") or []]
            (run_dir / "coordinate_audit.md").write_text(
                render_coordinate_audit_markdown(
                    audits,
                    project_name=project_name,
                    root=project_root,
                ),
                encoding="utf-8",
            )
        if hotspot_payload:
            hotspots = [ClashIncident.model_validate(item) for item in hotspot_payload.get("incidents") or []]
            (run_dir / "hotspot_incidents.md").write_text(
                render_hotspot_markdown(
                    hotspots,
                    project_name=project_name,
                    root=project_root,
                ),
                encoding="utf-8",
            )

    return 0


def _load_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_optional_json(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
