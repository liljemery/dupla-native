#!/usr/bin/env python3
"""Viewer local APS para SERENA 18 — ARQ intra-discipline clashes.

Levanta un servidor HTTP en localhost que sirve el Autodesk Viewer cargando
el plano ARQ desde el URN cacheado en aps_arq.json, con los clash markers
superpuestos como sprites magenta en la vista 2D.

Uso:
    PYTHONPATH=motor python motor/coordination/scripts/serve_serena18_clash_viewer.py
    PYTHONPATH=motor python motor/coordination/scripts/serve_serena18_clash_viewer.py --port 9090
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = REPO_ROOT / "backend" / ".env"

RUN_DIR = Path("var/coord_outputs/serena18_run")
APS_META = RUN_DIR / "aps_arq.json"
CLASH_JSON = RUN_DIR / "arq_intra_clash" / "clash_results.json"

APS_AUTH = "https://developer.api.autodesk.com/authentication/v2/token"
TWO_D_GUID = "6882be48-6626-5238-d3df-94e9f0a0019d"

SEV_COLOR = {
    "critical": "#D22626",
    "major": "#E65100",
    "minor": "#1565C0",
}


# ── credentials ────────────────────────────────────────────────────────────────

def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _get_token(cid: str, sec: str) -> tuple[str, int]:
    data = urllib.parse.urlencode({
        "client_id": cid,
        "client_secret": sec,
        "grant_type": "client_credentials",
        "scope": "data:read viewables:read",
    }).encode()
    req = urllib.request.Request(
        APS_AUTH, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=30)
    j = json.loads(resp.read())
    return j["access_token"], int(j.get("expires_in", 3500))


# ── clash data ─────────────────────────────────────────────────────────────────

def _load_clashes() -> list[dict]:
    if not CLASH_JSON.is_file():
        return []
    data = json.loads(CLASH_JSON.read_text())
    out = []
    for inc in data.get("incidents", []):
        rep = inc.get("representative") or {}
        b = inc["bounds_m"]
        out.append({
            "id": inc["incident_id"],
            "severity": inc["severity"],
            "color": SEV_COLOR.get(inc["severity"], "#888"),
            "layer_a": rep.get("layer_a", ""),
            "layer_b": rep.get("layer_b", ""),
            "centroid_m": inc["centroid_m"],
            "bounds_m": b,
        })
    return out


# ── HTML ───────────────────────────────────────────────────────────────────────

def _build_html(urn: str, viewable_guid: str, clashes: list[dict]) -> str:
    clashes_json = json.dumps(clashes, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <title>SERENA 18 — ARQ Clash Viewer</title>
  <link rel="stylesheet" href="https://developer.api.autodesk.com/modelderivative/v2/viewers/7.*/style.min.css"/>
  <script src="https://developer.api.autodesk.com/modelderivative/v2/viewers/7.*/viewer3D.min.js"></script>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: system-ui, sans-serif; background: #111; color: #eee;
           height: 100dvh; display: flex; flex-direction: column; overflow: hidden; }}
    #toolbar {{ display: flex; align-items: center; gap: 12px; padding: 8px 14px;
               background: #1a1a1a; border-bottom: 1px solid #333; flex-shrink: 0; font-size: 13px; }}
    #toolbar h1 {{ margin: 0; font-size: 14px; font-weight: 700; }}
    #toolbar select {{ background: #222; color: #eee; border: 1px solid #444; padding: 4px 8px;
                       border-radius: 6px; font-size: 12px; cursor: pointer; }}
    #toolbar label {{ font-size: 12px; color: #aaa; display: flex; align-items: center; gap: 6px; }}
    #status {{ font-size: 12px; color: #aaa; margin-left: auto; }}
    #legend {{ display: flex; gap: 10px; flex-shrink: 0; }}
    .badge {{ display: flex; align-items: center; gap: 5px; font-size: 11px; }}
    .dot {{ width: 10px; height: 10px; border-radius: 50%; }}
    #viewer {{ flex: 1; min-height: 0; background: #222; }}
    #info {{ position: fixed; bottom: 12px; right: 14px; background: #1e1e1e; border: 1px solid #444;
             border-radius: 8px; padding: 10px 14px; font-size: 12px; max-width: 320px;
             display: none; z-index: 999; }}
    #info h3 {{ margin: 0 0 6px; font-size: 13px; }}
    #info .pair {{ color: #d87; font-weight: 600; margin-bottom: 4px; }}
    #info .meta {{ color: #aaa; }}
    #info button {{ float: right; background: none; border: none; color: #aaa; cursor: pointer;
                    font-size: 16px; margin: -4px -6px 0 0; }}
  </style>
</head>
<body>
  <div id="toolbar">
    <h1>SERENA 18 — ARQ Clash Viewer</h1>
    <div id="legend">
      <div class="badge"><div class="dot" style="background:#D22626"></div>Critical</div>
      <div class="badge"><div class="dot" style="background:#E65100"></div>Major</div>
      <div class="badge"><div class="dot" style="background:#1565C0"></div>Minor</div>
    </div>
    <label>
      <input type="checkbox" id="toggleMarkers" checked> Mostrar clashes
    </label>
    <select id="sevFilter">
      <option value="">Todos</option>
      <option value="critical">Critical</option>
      <option value="major">Major</option>
      <option value="minor">Minor</option>
    </select>
    <div id="status">Inicializando…</div>
  </div>
  <div id="viewer"></div>
  <div id="info">
    <button onclick="document.getElementById('info').style.display='none'">✕</button>
    <h3 id="info-id"></h3>
    <div class="pair" id="info-pair"></div>
    <div class="meta" id="info-meta"></div>
  </div>

  <script>
  const URN = {json.dumps(urn)};
  const VIEWABLE_GUID = {json.dumps(viewable_guid)};
  const CLASHES = {clashes_json};

  let viewer = null;
  let overlayScene = null;
  let markers = [];
  let activeFilter = '';

  function status(msg) {{
    document.getElementById('status').textContent = msg;
  }}

  function getAccessToken(callback) {{
    fetch('/api/token')
      .then(r => r.json())
      .then(d => callback(d.access_token, d.expires_in || 3500))
      .catch(e => status('Error token: ' + e));
  }}

  // ── marker geometry ──────────────────────────────────────────────────────
  function makeMarkers(clashes, filter) {{
    if (overlayScene) {{
      viewer.impl.removeOverlayScene('clashes');
      overlayScene = null;
      markers = [];
    }}
    if (!document.getElementById('toggleMarkers').checked) return;

    const THREE = Autodesk.Viewing.Private.THREE;
    viewer.impl.createOverlayScene('clashes');
    overlayScene = viewer.impl.overlayScenes['clashes'];

    CLASHES.forEach((cl, i) => {{
      if (filter && cl.severity !== filter) return;

      const [mx, my] = cl.centroid_m;
      const color = new THREE.Color(cl.color);

      // Sphere marker
      const geo = new THREE.SphereGeometry(0.3, 12, 12);
      const mat = new THREE.MeshBasicMaterial({{ color, transparent: true, opacity: 0.85 }});
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(mx, my, 0.1);
      mesh.userData = cl;
      viewer.impl.addOverlay('clashes', mesh);
      markers.push(mesh);

      // Ring outline
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(0.35, 0.55, 24),
        new THREE.MeshBasicMaterial({{ color, side: THREE.DoubleSide }})
      );
      ring.position.set(mx, my, 0.15);
      viewer.impl.addOverlay('clashes', ring);
    }});
    viewer.impl.invalidate(true);
    status(`${{markers.length}} clash marker(s) activos`);
  }}

  // ── pick on click ────────────────────────────────────────────────────────
  function onCanvasClick(e) {{
    if (!overlayScene) return;
    const THREE = Autodesk.Viewing.Private.THREE;
    const rect = viewer.container.getBoundingClientRect();
    const ndc = {{
      x:  ((e.clientX - rect.left)  / rect.width)  * 2 - 1,
      y: -((e.clientY - rect.top) / rect.height) * 2 + 1,
    }};
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, viewer.impl.camera);
    const hits = ray.intersectObjects(markers, false);
    if (!hits.length) return;
    const cl = hits[0].object.userData;
    const panel = document.getElementById('info');
    document.getElementById('info-id').textContent = cl.id + ' · ' + cl.severity.toUpperCase();
    document.getElementById('info-pair').textContent = cl.layer_a + ' vs ' + cl.layer_b;
    document.getElementById('info-meta').textContent =
      'Centroide: (' + cl.centroid_m.map(v => v.toFixed(2)).join(', ') + ') m';
    panel.style.display = 'block';
  }}

  // ── viewer bootstrap ─────────────────────────────────────────────────────
  function initViewer() {{
    const options = {{
      env: 'AutodeskProduction',
      api: 'derivativeV2',
      getAccessToken,
    }};
    Autodesk.Viewing.Initializer(options, () => {{
      const container = document.getElementById('viewer');
      viewer = new Autodesk.Viewing.GuiViewer3D(container);
      viewer.start();
      viewer.setTheme('dark-theme');

      const docId = 'urn:' + URN;
      Autodesk.Viewing.Document.load(docId,
        doc => {{
          // prefer 2D View by GUID
          const all = doc.getRoot().search({{ type: 'geometry' }});
          const target = all.find(v => v.data && v.data.guid === VIEWABLE_GUID)
                      || all.find(v => v.data && v.data.role === '2d')
                      || doc.getRoot().getDefaultGeometry();

          status('Cargando ' + (target.data && target.data.name || '2D View') + '…');
          viewer.loadDocumentNode(doc, target).then(() => {{
            viewer.fitToView();
            status('Plano listo · generando markers…');
            makeMarkers(CLASHES, activeFilter);
            viewer.container.addEventListener('click', onCanvasClick);
          }});
        }},
        (code, msg) => status('Error cargando modelo: ' + code + ' ' + msg)
      );
    }});
  }}

  document.getElementById('toggleMarkers').addEventListener('change', () => makeMarkers(CLASHES, activeFilter));
  document.getElementById('sevFilter').addEventListener('change', e => {{
    activeFilter = e.target.value;
    makeMarkers(CLASHES, activeFilter);
  }});

  initViewer();
  </script>
</body>
</html>"""


# ── HTTP server ────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    _html: str = ""
    _clashes: list[dict] = []
    _env: dict[str, str] = {}

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path

        if path == "/":
            self._send(Handler._html.encode(), "text/html; charset=utf-8")

        elif path == "/api/token":
            try:
                cid = Handler._env.get("CLIENT_ID") or Handler._env.get("APS_CLIENT_ID", "")
                sec = Handler._env.get("CLIENT_SECRET") or Handler._env.get("APS_CLIENT_SECRET", "")
                tok, exp = _get_token(cid, sec)
                body = json.dumps({"access_token": tok, "expires_in": exp}).encode()
                self._send(body, "application/json")
            except Exception as exc:
                body = json.dumps({"error": str(exc)}).encode()
                self._send(body, "application/json", 500)

        elif path == "/api/clashes":
            body = json.dumps(Handler._clashes, ensure_ascii=False).encode()
            self._send(body, "application/json")

        else:
            self.send_error(404)


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Viewer APS local — SERENA 18 ARQ clashes")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-open", action="store_true", help="No abrir browser automáticamente")
    args = parser.parse_args()

    if not APS_META.is_file():
        raise SystemExit(f"[!] No se encontró {APS_META}. Corre aps_translate_arq.py primero.")

    meta = json.loads(APS_META.read_text())
    urn = meta["urn"]
    clashes = _load_clashes()
    env = _load_env()

    Handler._clashes = clashes
    Handler._env = env
    Handler._html = _build_html(urn, TWO_D_GUID, clashes)

    n_sev = {s: sum(1 for c in clashes if c["severity"] == s) for s in ("critical", "major", "minor")}
    url = f"http://127.0.0.1:{args.port}"

    print(f"[viewer] URN     : {urn[:60]}…")
    print(f"[viewer] Clashes : {len(clashes)} total — {n_sev}")
    print(f"[viewer] URL     : {url}")
    print("[viewer] Ctrl+C para detener")

    if not args.no_open:
        webbrowser.open(url)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[viewer] Detenido.")


if __name__ == "__main__":
    main()
