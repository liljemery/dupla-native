#!/usr/bin/env python3
"""Servidor local con Autodesk Viewer para DWGs traducidos en APS (SERENA 18)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

MOTOR_ROOT = Path(__file__).resolve().parents[2]
MONOREPO_ROOT = MOTOR_ROOT.parent
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

load_dotenv(MONOREPO_ROOT / "backend" / ".env")
load_dotenv(MOTOR_ROOT / ".env")

from aps_integration.aps_auth import get_aps_token
from aps_integration.model_derivative import (
    get_manifest,
    inspect_manifest_derivatives,
    urn_from_object_id,
)
from aps_integration.oss_manager import APS_BUCKET_NAME

_SCRATCH_PATH = Path(__file__).resolve().parent / "scratch.py"
_spec = importlib.util.spec_from_file_location("scratch_pipeline", _SCRATCH_PATH)
assert _spec and _spec.loader
_scratch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scratch)
DEFAULT_RUTA_RAIZ = _scratch.DEFAULT_RUTA_RAIZ
escanear_dwgs_serena = _scratch.escanear_dwgs_serena

VIEWER_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SERENA 18 — APS Viewer</title>
  <link rel="stylesheet" href="https://developer.api.autodesk.com/modelderivative/v2/viewers/7.*/style.min.css" />
  <script src="https://developer.api.autodesk.com/modelderivative/v2/viewers/7.*/viewer3D.min.js"></script>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, sans-serif; background: #111; color: #eee; height: 100dvh; display: flex; }
    aside { width: 360px; border-right: 1px solid #333; display: flex; flex-direction: column; min-height: 0; }
    header { padding: 12px 14px; border-bottom: 1px solid #333; }
    header h1 { margin: 0 0 6px; font-size: 15px; }
    header p { margin: 0; font-size: 12px; color: #aaa; }
    #search { width: 100%; margin-top: 10px; padding: 8px 10px; border-radius: 8px; border: 1px solid #444; background: #1a1a1a; color: #eee; }
    #list { flex: 1; overflow: auto; padding: 8px; }
    .item { display: block; width: 100%; text-align: left; border: 1px solid #333; background: #1a1a1a; color: #eee; border-radius: 8px; padding: 10px; margin-bottom: 8px; cursor: pointer; }
    .item:hover { border-color: #666; }
    .item.active { border-color: #4da3ff; background: #172433; }
    .item[disabled] { opacity: 0.45; cursor: not-allowed; }
    .name { font-size: 13px; font-weight: 600; word-break: break-word; }
    .meta { margin-top: 4px; font-size: 11px; color: #aaa; }
    .ok { color: #6fdc8c; }
    .pending { color: #f5c451; }
    .bad { color: #ff7b7b; }
    main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
    #toolbar { padding: 10px 14px; border-bottom: 1px solid #333; font-size: 13px; color: #ccc; }
    #viewer { flex: 1; min-height: 0; background: #222; }
    #status { padding: 8px 14px; font-size: 12px; color: #aaa; border-top: 1px solid #333; }
  </style>
</head>
<body>
  <aside>
    <header>
      <h1>SERENA 18 — APS Viewer</h1>
      <p id="summary">Cargando catálogo…</p>
      <input id="search" type="search" placeholder="Buscar DWG…" />
    </header>
    <div id="list"></div>
  </aside>
  <main>
    <div id="toolbar">Selecciona un plano traducido (status success) para abrirlo.</div>
    <div id="viewer"></div>
    <div id="status">Inicializando viewer…</div>
  </main>
  <script>
    let viewer = null;
    let models = [];
    let activeUrn = null;

    function statusClass(status) {
      if (status === 'success') return 'ok';
      if (status === 'failed' || status === 'timeout') return 'bad';
      return 'pending';
    }

    function renderList(filter = '') {
      const list = document.getElementById('list');
      const q = filter.trim().toLowerCase();
      list.innerHTML = '';
      const filtered = models.filter(m => !q || m.name.toLowerCase().includes(q) || m.relative_path.toLowerCase().includes(q));
      document.getElementById('summary').textContent =
        `${models.filter(m => m.status === 'success').length}/${models.length} listos para ver`;

      for (const model of filtered) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'item' + (model.urn === activeUrn ? ' active' : '');
        btn.disabled = model.status !== 'success';
        btn.innerHTML =
          `<div class="name">${model.name}</div>` +
          `<div class="meta ${statusClass(model.status)}">${model.status} · ${model.progress}</div>` +
          `<div class="meta">${model.relative_path}</div>`;
        btn.onclick = () => loadModel(model);
        list.appendChild(btn);
      }
    }

    async function fetchModels(refresh = false) {
      const url = refresh ? '/api/models?refresh=1' : '/api/models';
      const res = await fetch(url);
      models = await res.json();
      renderList(document.getElementById('search').value);
    }

    function getAccessToken(onTokenReady) {
      fetch('/api/token')
        .then(r => r.json())
        .then(data => onTokenReady(data.access_token, data.expires_in || 3500))
        .catch(err => {
          document.getElementById('status').textContent = 'Error token: ' + err;
        });
    }

    function initViewer() {
      const options = {
        env: 'AutodeskProduction',
        api: 'derivativeV2',
        getAccessToken,
      };
      Autodesk.Viewing.Initializer(options, () => {
        const container = document.getElementById('viewer');
        viewer = new Autodesk.Viewing.GuiViewer3D(container, { extensions: ['Autodesk.DocumentBrowser'] });
        viewer.start();
        viewer.setTheme('dark-theme');
        document.getElementById('status').textContent = 'Viewer listo.';
        fetchModels(false);
        setInterval(() => fetchModels(true), 30000);
      });
    }

    function loadModel(model) {
      if (!viewer || model.status !== 'success') return;
      activeUrn = model.urn;
      renderList(document.getElementById('search').value);
      document.getElementById('toolbar').textContent = model.name;
      document.getElementById('status').textContent = 'Cargando ' + model.name + '…';

      const documentId = 'urn:' + model.urn;
      Autodesk.Viewing.Document.load(
        documentId,
        (doc) => {
          const defaultModel = doc.getRoot().getDefaultGeometry();
          viewer.loadDocumentNode(doc, defaultModel).then(() => {
            document.getElementById('status').textContent = 'Mostrando ' + model.name;
            viewer.fitToView();
          });
        },
        (code, message) => {
          document.getElementById('status').textContent = 'Error cargando: ' + code + ' ' + message;
        }
      );
    }

    document.getElementById('search').addEventListener('input', (e) => renderList(e.target.value));
    initViewer();
  </script>
</body>
</html>
"""


def build_model_catalog(
    ruta_raiz: str,
    bucket_name: str,
    *,
    refresh_status: bool = False,
    cached: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    token = get_aps_token() if refresh_status or not cached else None
    paths = escanear_dwgs_serena(ruta_raiz)
    catalog: list[dict[str, str]] = []
    cached_by_urn = {item["urn"]: item for item in (cached or [])}

    for path in paths:
        name = os.path.basename(path)
        object_name = name
        urn = urn_from_object_id(bucket_name, object_name)
        rel = os.path.relpath(path, ruta_raiz)
        entry = {
            "name": name,
            "relative_path": rel,
            "local_path": path,
            "urn": urn,
            "status": "unknown",
            "progress": "—",
        }
        if not refresh_status and urn in cached_by_urn:
            prev = cached_by_urn[urn]
            entry["status"] = prev.get("status", "unknown")
            entry["progress"] = prev.get("progress", "—")
        elif refresh_status and token:
            try:
                manifest = get_manifest(token, urn)
                info = inspect_manifest_derivatives(manifest)
                entry["status"] = str(info.get("manifest_status") or "unknown")
                entry["progress"] = str(info.get("manifest_progress") or "—")
            except Exception as exc:
                entry["status"] = "error"
                entry["progress"] = str(exc)[:120]
        catalog.append(entry)

    catalog.sort(key=lambda item: item["relative_path"].lower())
    return catalog


class ViewerHandler(BaseHTTPRequestHandler):
    catalog_cache: list[dict[str, str]] = []
    ruta_raiz: str = DEFAULT_RUTA_RAIZ
    bucket_name: str = APS_BUCKET_NAME

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(VIEWER_HTML)
            return

        if parsed.path == "/api/token":
            try:
                token = get_aps_token()
                self._send_json({"access_token": token, "expires_in": 3500})
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if parsed.path == "/api/models":
            refresh = parse_qs(parsed.query).get("refresh", ["0"])[0] == "1"
            try:
                ViewerHandler.catalog_cache = build_model_catalog(
                    self.ruta_raiz,
                    self.bucket_name,
                    refresh_status=refresh or not ViewerHandler.catalog_cache,
                    cached=ViewerHandler.catalog_cache,
                )
                self._send_json(ViewerHandler.catalog_cache)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        self.send_error(404)


def main() -> int:
    parser = argparse.ArgumentParser(description="Visor local APS para DWGs de SERENA 18.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--ruta-raiz", default=DEFAULT_RUTA_RAIZ)
    args = parser.parse_args()

    bucket_name = os.getenv("APS_BUCKET_NAME", APS_BUCKET_NAME)
    if not bucket_name:
        print("[-] APS_BUCKET_NAME no configurado en backend/.env")
        return 1

    ViewerHandler.ruta_raiz = args.ruta_raiz
    ViewerHandler.bucket_name = bucket_name

    print(f"[*] Bucket: {bucket_name}")
    print(f"[*] Raíz DWG: {args.ruta_raiz}")
    print(f"[*] Abre http://127.0.0.1:{args.port}")
    print("[*] Ctrl+C para detener")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), ViewerHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Viewer detenido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
