"""Check APS PDF derivatives for a cached DWG extraction result.

Usage:
    python scripts/diagnostic_check_pdf_derivatives.py cache/<sha256>/ APS_TOKEN
"""

from __future__ import annotations

import base64
import json
import os
import sys

import httpx


def _find_urn(payload) -> str:
    if isinstance(payload, dict):
        for key in ("urn", "objectId", "id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        nested = payload.get("data")
        if nested is not None:
            found = _find_urn(nested)
            if found:
                return found
        for value in payload.values():
            found = _find_urn(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_urn(item)
            if found:
                return found
    return ""


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: diagnostic_check_pdf_derivatives.py CACHE_DIR APS_TOKEN", file=sys.stderr)
        return 2

    cache_dir = sys.argv[1]
    token = sys.argv[2]
    raw_path = os.path.join(cache_dir, "raw.json")
    with open(raw_path, encoding="utf-8") as f:
        raw = json.load(f)

    urn = _find_urn(raw)
    if urn and not urn.startswith("urn:") and not urn.startswith("dXJu"):
        urn = base64.urlsafe_b64encode(urn.encode()).decode().rstrip("=")

    print(f"URN: {urn[:40]}...")
    url = f"https://developer.api.autodesk.com/modelderivative/v2/designdata/{urn}/manifest"
    response = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    print(f"Manifest status: {response.status_code}")
    if response.status_code != 200:
        print(response.text[:500])
        return 1

    manifest = response.json()
    print(f"Translation status: {manifest.get('status')}")
    print(f"Progress: {manifest.get('progress')}")
    derivatives = manifest.get("derivatives", [])
    print(f"\nDerivatives found: {len(derivatives)}")
    for derivative in derivatives:
        print(f"\n  outputType: {derivative.get('outputType')}")
        print(f"  status:     {derivative.get('status')}")
        print("  children:")
        for child in derivative.get("children", [])[:5]:
            print(
                f"    role={child.get('role')}  type={child.get('type')}  "
                f"mime={child.get('mime')}  urn={str(child.get('urn', ''))[:40]}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
