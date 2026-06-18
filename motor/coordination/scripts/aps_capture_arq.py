"""Headless APS Viewer capture for the ARQ SERENA-18 2D plan + clash overlay.

Reads the cached URN (aps_arq.json), builds a clashes payload from the intra-clash
incidents (meters -> mm, factor 1000), runs viewer-engine/capture.js on the 2D
modelspace viewable, and writes:
    arq_intra_clash/aps_plan.png         (real APS screenshot)
    arq_intra_clash/aps_plan.png.boxes.json
    arq_intra_clash/aps_plan.png.diag.json

Then overlays the projected boxes on the screenshot with PIL ->
    arq_intra_clash/aps_plan_annotated.png
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RUN_DIR = Path("var/coord_outputs/serena18_run")
OUT_DIR = RUN_DIR / "arq_intra_clash"
APS_META = RUN_DIR / "aps_arq.json"
CLASH_JSON = OUT_DIR / "clash_results.json"
ENGINE_DIR = Path("backend/viewer-engine")
CAPTURE = ENGINE_DIR / "capture.js"
TWO_D_VIEW_GUID = "6882be48-6626-5238-d3df-94e9f0a0019d"  # role=2d name="2D View" (paper 17x11)
THREE_D_VIEW_GUID = "3bb36b05-6fb7-1fd0-3c58-d83a4e8d4042"  # role=3d (real model coords, meters)

SEV_COLOR = {"critical": (220, 38, 38), "major": (230, 81, 0), "minor": (21, 101, 192)}


def _token() -> str:
    helpers = Path("motor/coordination/scripts/aps_translate_arq.py").read_text().split("def main")[0]
    ns: dict = {}
    exec(helpers, ns)  # noqa: S102 - trusted local helper
    env = ns["load_env"]()
    return ns["get_token"](env["CLIENT_ID"], env["CLIENT_SECRET"])


def build_clashes() -> list[dict]:
    data = json.loads(CLASH_JSON.read_text())
    clashes = []
    for inc in data.get("incidents", []):
        b = inc["bounds_m"]
        c = inc["centroid_m"]
        clashes.append({
            "bounds_mm": [b[0] * 1000.0, b[1] * 1000.0, b[2] * 1000.0, b[3] * 1000.0],
            "centroid_mm": [c[0] * 1000.0, c[1] * 1000.0],
            "units_to_mm_factor": 1000.0,
            "clash_type": inc["severity"],
            "incident_id": inc["incident_id"],
        })
    return clashes


def capture(width: int = 3400, height: int = 2400) -> dict:
    meta = json.loads(APS_META.read_text())
    urn = meta["urn"]
    token = _token()
    out_png = (OUT_DIR / "aps_plan.png").resolve()
    guid = THREE_D_VIEW_GUID if "--3d" in sys.argv else TWO_D_VIEW_GUID
    clashes = build_clashes()
    clashes_file = out_png.with_suffix(".clashes.json")
    clashes_file.write_text(json.dumps(clashes, ensure_ascii=False, indent=2))
    cmd = [
        "node", str(CAPTURE.resolve()),
        "--urn", urn,
        "--token", token,
        "--output", str(out_png),
        "--width", str(width),
        "--height", str(height),
        "--timeout", "180000",
        "--viewable-guid", guid,
        "--clashes-file", str(clashes_file),
    ]
    print("[capture] running headless APS viewer on 2D View…")
    r = subprocess.run(cmd, cwd=str(ENGINE_DIR.resolve()), capture_output=True, text=True, timeout=240)
    for line in (r.stdout or "").splitlines():
        if line.strip():
            print("  ", line)
    if r.returncode != 0:
        print("[capture] STDERR:", (r.stderr or "")[:1500])
        raise SystemExit(f"capture.js failed rc={r.returncode}")
    return json.loads(Path(str(out_png) + ".diag.json").read_text())


def main() -> None:
    diag = capture()
    print("[capture] DIAG:")
    print(json.dumps(diag, indent=2)[:1200])
    boxes_path = OUT_DIR / "aps_plan.png.boxes.json"
    if boxes_path.is_file():
        boxes = json.loads(boxes_path.read_text())
        print(f"[capture] projected boxes: {len(boxes)}")
        for b in boxes[:3]:
            print("   ", b)


if __name__ == "__main__":
    main()
