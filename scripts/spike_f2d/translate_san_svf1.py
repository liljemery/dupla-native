"""Mini-spike A1 (variante SVF v1): traduce el SAN a SVF v1 para alinear dbIds
de geometría 2D con los de propiedades (capas). Reutiliza el objeto ya subido.

Escribe urn_svf1.json.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

MONOREPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MONOREPO_ROOT / "motor"))

import requests  # noqa: E402

from aps_integration.aps_auth import get_aps_token  # noqa: E402
from aps_integration.model_derivative import (  # noqa: E402
    MD_URL,
    get_manifest,
    inspect_manifest_derivatives,
    urn_from_object_id,
)

BUCKET = "dupla_spike_f2d_v1"
OBJECT = "15.04.2026 LAS NASAS 09 HS-AGUA POTABLE.dwg"
OUT = Path(__file__).resolve().parent / "urn_svf1.json"


def main() -> int:
    token = get_aps_token()
    urn = urn_from_object_id(BUCKET, OBJECT)

    payload = {
        "input": {"urn": urn},
        "output": {"formats": [{"type": "svf", "views": ["2d", "3d"]}]},
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(f"{MD_URL}/job", json=payload, headers=headers, timeout=60)
    print("[SVF1] submit status", r.status_code, r.text[:200])
    if r.status_code not in (200, 201, 202):
        return 1

    deadline = time.time() + 1800
    status = "pending"
    while time.time() < deadline:
        m = get_manifest(token, urn)
        info = inspect_manifest_derivatives(m)
        status = str(info.get("manifest_status"))
        prog = str(info.get("manifest_progress"))
        print(f"[SVF1] status={status} progress={prog} roles={info.get('roles')}")
        if status in ("success", "failed", "timeout"):
            break
        time.sleep(10)

    m = get_manifest(token, urn)
    info = inspect_manifest_derivatives(m)
    guids = []

    def walk(node, parent_role=None):
        if isinstance(node, dict):
            role = node.get("role") or parent_role
            if node.get("guid") and node.get("type") == "geometry":
                guids.append({"guid": node.get("guid"), "role": role, "name": node.get("name")})
            for c in (node.get("derivatives") or []):
                walk(c, role)
            for c in (node.get("children") or []):
                walk(c, role)
        elif isinstance(node, list):
            for it in node:
                walk(it, parent_role)

    walk(m)
    OUT.write_text(
        json.dumps(
            {"urn": urn, "object_name": OBJECT, "bucket": BUCKET,
             "manifest_status": status, "viewables": guids},
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[SVF1] guardado {OUT} status={status} viewables={len(guids)}")
    return 0 if status == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
