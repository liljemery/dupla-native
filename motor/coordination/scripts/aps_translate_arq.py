"""Upload the ARQ SERENA-18 DWG to APS OSS and translate it to SVF2 (2D), then
cache the resulting URN so the headless viewer capture can reuse it.

Self-contained (stdlib only) so it does not pull the backend app import chain.
Credentials are read from backend/.env (CLIENT_ID / CLIENT_SECRET / APS_BUCKET_NAME).

Output: var/coord_outputs/serena18_run/aps_arq.json
    { "urn": "<base64>", "bucket_key": "...", "object_key": "...", "status": "success" }
"""

from __future__ import annotations

import base64
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path("backend/.env")
DWG_PATH = Path(
    "/Users/samuelfernandez/Downloads/SERENA 18/REVISION/PLANOS REVISADOS/"
    "ARQUITECTONICOS/05. MAYO 2024/2208-Serena18-ID-Base.dwg"
)
OUT_PATH = Path("var/coord_outputs/serena18_run/aps_arq.json")
OBJECT_KEY = "serena18-arq-id-base.dwg"

APS_AUTH = "https://developer.api.autodesk.com/authentication/v2/token"
APS_OSS = "https://developer.api.autodesk.com/oss/v2"
APS_MD = "https://developer.api.autodesk.com/modelderivative/v2"


def load_env() -> dict:
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def normalize_bucket_key(raw: str) -> str:
    s = "".join(c if (c.isalnum() or c == "-") else "-" for c in raw.strip().lower())
    s = s.strip("-")[:63]
    return f"dupla-{s}"[:63] if len(s) < 3 else s


def req(method: str, url: str, token: str | None = None, *, data=None, headers=None, timeout=120):
    h = dict(headers or {})
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=timeout)
        body = resp.read()
        return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def get_token(cid: str, sec: str) -> str:
    data = urllib.parse.urlencode({
        "client_id": cid, "client_secret": sec, "grant_type": "client_credentials",
        "scope": "data:read data:write bucket:read bucket:create viewables:read",
    }).encode()
    status, body = req("POST", APS_AUTH, data=data,
                       headers={"Content-Type": "application/x-www-form-urlencoded"})
    if status != 200:
        raise SystemExit(f"token failed {status}: {body[:300]}")
    return json.loads(body)["access_token"]


def ensure_bucket(token: str, bucket: str, region: str, policy: str) -> None:
    status, _ = req("GET", f"{APS_OSS}/buckets/{urllib.parse.quote(bucket, safe='')}/details", token)
    if status == 200:
        return
    body = json.dumps({"bucketKey": bucket, "policyKey": policy, "region": region}).encode()
    status, resp = req("POST", f"{APS_OSS}/buckets", token, data=body,
                       headers={"Content-Type": "application/json"})
    if status not in (200, 201, 409):
        raise SystemExit(f"bucket create failed {status}: {resp[:300]}")


def upload(token: str, bucket: str, object_key: str, path: Path) -> None:
    enc = urllib.parse.quote(object_key, safe="")
    base = f"{APS_OSS}/buckets/{urllib.parse.quote(bucket, safe='')}/objects/{enc}/signeds3upload"
    status, body = req("GET", base + "?firstPart=1&parts=1&minutesExpiration=45", token)
    if status != 200:
        raise SystemExit(f"signeds3 GET failed {status}: {body[:300]}")
    j = json.loads(body)
    upload_key, put_url = j["uploadKey"], j["urls"][0]
    raw = path.read_bytes()
    status, resp = req("PUT", put_url, data=raw,
                       headers={"Content-Type": "application/octet-stream"}, timeout=600)
    if status not in (200, 201, 204):
        raise SystemExit(f"S3 PUT failed {status}: {resp[:300]}")
    body = json.dumps({"uploadKey": upload_key, "size": len(raw)}).encode()
    status, resp = req("POST", base, token, data=body, headers={"Content-Type": "application/json"})
    if status not in (200, 201):
        raise SystemExit(f"upload complete failed {status}: {resp[:300]}")


def urn_for(bucket: str, object_key: str) -> str:
    raw = f"urn:adsk.objects:os.object:{bucket}/{object_key}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def manifest(token: str, urn: str) -> dict | None:
    status, body = req("GET", f"{APS_MD}/designdata/{urllib.parse.quote(urn, safe='')}/manifest", token)
    if status == 404:
        return None
    if status != 200:
        return {"status": f"http_{status}", "body": body[:300].decode(errors="ignore")}
    return json.loads(body)


def translate(token: str, urn: str) -> None:
    body = json.dumps({
        "input": {"urn": urn},
        "output": {"formats": [{"type": "svf", "views": ["2d", "3d"]}]},
    }).encode()
    status, resp = req("POST", f"{APS_MD}/designdata/job", token, data=body,
                       headers={"Content-Type": "application/json", "x-ads-force": "true"})
    if status not in (200, 201, 202):
        raise SystemExit(f"translate job failed {status}: {resp[:400]}")


def main() -> None:
    env = load_env()
    cid = env.get("CLIENT_ID") or env.get("APS_CLIENT_ID")
    sec = env.get("CLIENT_SECRET") or env.get("APS_CLIENT_SECRET")
    bucket = normalize_bucket_key(env.get("APS_BUCKET_NAME") or "dupla-coord")
    region = (env.get("APS_REGION") or "US").upper()
    policy = (env.get("APS_BUCKET_POLICY") or "transient").lower()

    token = get_token(cid, sec)
    print(f"[aps] token ok; bucket={bucket} region={region} policy={policy}")
    urn = urn_for(bucket, OBJECT_KEY)

    m = manifest(token, urn)
    st = (m or {}).get("status", "missing")
    if st == "success":
        print("[aps] manifest already success; reusing URN")
    else:
        ensure_bucket(token, bucket, region, policy)
        print(f"[aps] uploading {DWG_PATH.name} ({DWG_PATH.stat().st_size} bytes)…")
        upload(token, bucket, OBJECT_KEY, DWG_PATH)
        time.sleep(2)
        urn = urn_for(bucket, OBJECT_KEY)
        print("[aps] submitting SVF2 translation job…")
        translate(token, urn)
        deadline = time.time() + 600
        while time.time() < deadline:
            m = manifest(token, urn)
            st = (m or {}).get("status", "missing")
            prog = (m or {}).get("progress", "")
            print(f"[aps] manifest status={st} progress={prog}")
            if st == "success":
                break
            if st in ("failed", "timeout"):
                raise SystemExit(f"translation {st}: {json.dumps(m)[:600]}")
            time.sleep(8)
        else:
            raise SystemExit("translation timed out after 600s")

    # list 2d/3d viewables for reference
    roles = []
    def walk(n, d=0):
        if d > 12 or not isinstance(n, (dict, list)):
            return
        if isinstance(n, dict):
            if n.get("role"):
                roles.append((n.get("role"), n.get("name"), n.get("guid")))
            for c in n.get("children") or []:
                walk(c, d + 1)
        else:
            for c in n:
                walk(c, d)
    for der in (m or {}).get("derivatives") or []:
        walk(der)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "urn": urn, "bucket_key": bucket, "object_key": OBJECT_KEY,
        "status": st, "viewables": [{"role": r, "name": nm, "guid": g} for r, nm, g in roles[:60]],
    }, ensure_ascii=False, indent=2))
    print(f"[aps] saved -> {OUT_PATH}")
    print(f"[aps] URN = {urn}")
    print(f"[aps] viewables: {len(roles)}")
    for r, nm, g in roles[:12]:
        print(f"    role={r} name={nm} guid={g}")


if __name__ == "__main__":
    main()
