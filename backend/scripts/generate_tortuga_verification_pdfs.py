#!/usr/bin/env python3
"""Generate PDFs from real Dupla analysis_output for verification.

Run with Dupla repo available at DUPLA_ROOT:

  cd backend && source .venv/bin/activate
  DUPLA_ROOT=/path/to/Dupla python scripts/generate_tortuga_verification_pdfs.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.services.clash_export_service import ClashExportService


def _load_analysis_dir(analysis_dir: Path) -> dict:
    primary = json.loads((analysis_dir / "primary_incidents.json").read_text(encoding="utf-8"))
    context = json.loads((analysis_dir / "coordination_report_context.json").read_text(encoding="utf-8"))
    pair_schedule_path = analysis_dir / "pair_schedule.json"
    pair_schedule = (
        json.loads(pair_schedule_path.read_text(encoding="utf-8"))
        if pair_schedule_path.exists()
        else {"pairs": []}
    )
    revision_md = ""
    for path in analysis_dir.glob("REVISION_CLASHES*.md"):
        revision_md = path.read_text(encoding="utf-8")
        break
    return {
        "primary_incidents": json.dumps(primary, ensure_ascii=False),
        "coordination_context": json.dumps(context, ensure_ascii=False),
        "pair_schedule": json.dumps(pair_schedule, ensure_ascii=False),
        "revision_md": revision_md,
        "output_dir": str(analysis_dir),
        "analyzed_documents": [],
    }


def main() -> None:
    candidates = [Path("/dupla/analysis_output/serena18_analysis_06")]
    analysis_dir = next((p for p in candidates if p.exists()), None)
    if analysis_dir is None:
        print("No analysis_output directory found. Mount Dupla at /dupla or run from monorepo.", file=sys.stderr)
        sys.exit(1)

    meta = {
        "project_name": "Serena 18 verification",
        "folder_name": "TORTUGA_C40",
        "user_display": "Verification",
        "run_date": "2026-05-22",
        "run_sequence": 1,
    }
    artifacts = _load_analysis_dir(analysis_dir)
    svc = ClashExportService(session=None)  # type: ignore[arg-type]
    out = Path(__file__).resolve().parents[1] / "var" / "sample_pdfs"
    out.mkdir(parents=True, exist_ok=True)
    human = svc.build_clash_human_pdf(meta=meta, artifacts=artifacts)
    tech = svc.build_clash_technical_pdf(meta=meta, artifacts=artifacts)
    (out / "TORTUGA_C40_human.pdf").write_bytes(human)
    (out / "TORTUGA_C40_technical.pdf").write_bytes(tech)
    print(f"Wrote {out / 'TORTUGA_C40_human.pdf'}")
    print(f"Wrote {out / 'TORTUGA_C40_technical.pdf'}")


if __name__ == "__main__":
    main()
