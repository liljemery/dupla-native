"""Mini-spike A1: re-traduce el DWG SAN a SVF2 y reporta el URN con derivados vivos.

Reutiliza los módulos del motor (auth, OSS, model derivative). Se traduce SOLO el
archivo más pequeño (SAN) para minimizar consumo de cuota APS durante el spike.

Salida: imprime y guarda en scripts/spike_f2d/urn.json el URN base64 listo para el Viewer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MONOREPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MONOREPO_ROOT / "motor"))

from aps_integration.aps_auth import get_aps_token  # noqa: E402
from aps_integration.model_derivative import (  # noqa: E402
    extract_dwg_data,
    get_manifest,
    inspect_manifest_derivatives,
    urn_from_object_id,
)
from aps_integration.oss_manager import create_bucket, upload_file_to_bucket  # noqa: E402

SAN_DWG = Path(
    "/Users/thewizard/Downloads/NASAS 9 DUPLA/SANITARIO/15.04.2026 LAS NASAS 09 HS-AGUA POTABLE.dwg"
)
BUCKET = "dupla_spike_f2d_v1"
OUT = Path(__file__).resolve().parent / "urn.json"


def main() -> int:
    if not SAN_DWG.is_file():
        print(f"[ERROR] No existe el DWG SAN: {SAN_DWG}")
        return 1

    token = get_aps_token()
    create_bucket(token, BUCKET)

    object_name = upload_file_to_bucket(token, BUCKET, str(SAN_DWG))
    if not object_name:
        print("[ERROR] Falló la subida del DWG.")
        return 1

    urn = urn_from_object_id(BUCKET, object_name)
    print(f"[SPIKE] object_name={object_name}")
    print(f"[SPIKE] urn={urn}")

    # Traducción 2D a SVF2 (espera a que termine).
    extract_dwg_data(
        token,
        BUCKET,
        object_name,
        views=("2d",),
        translation_timeout_seconds=1800,
        poll_interval_seconds=10,
    )

    manifest = get_manifest(token, urn)
    info = inspect_manifest_derivatives(manifest)
    print(f"[SPIKE] manifest_status={info.get('manifest_status')} roles={info.get('roles')}")

    # Extrae los GUID de las vistas 2D (viewables) para cargar en el Viewer.
    guids: list[dict] = []

    def walk(node, parent_role=None):
        if isinstance(node, dict):
            role = node.get("role") or parent_role
            if node.get("guid") and (node.get("type") == "geometry" or role in {"2d", "3d"}):
                guids.append(
                    {
                        "guid": node.get("guid"),
                        "role": role,
                        "name": node.get("name"),
                        "mime": node.get("mime"),
                        "type": node.get("type"),
                    }
                )
            for c in (node.get("derivatives") or []):
                walk(c, role)
            for c in (node.get("children") or []):
                walk(c, role)
        elif isinstance(node, list):
            for it in node:
                walk(it, parent_role)

    walk(manifest)

    payload = {
        "urn": urn,
        "object_name": object_name,
        "bucket": BUCKET,
        "manifest_status": info.get("manifest_status"),
        "viewables": guids,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[SPIKE] Guardado {OUT}")
    print(json.dumps(payload, indent=2)[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
