"""Download APS f2d/property-db resources and query layers from SQLite PropertyDatabase."""

from __future__ import annotations

import gzip
import logging
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from aps_integration.model_derivative import MD_URL, _iter_manifest_nodes, get_manifest

logger = logging.getLogger("dupla.aps.f2d_resources")

INCHES_TO_MM = 25.4


def _resolve_token(token: str | dict[str, Any]) -> str:
    if isinstance(token, dict):
        return str(token.get("access_token") or token.get("token") or "")
    return str(token)


def _download_derivative(token: str, model_urn: str, derivative_urn: str) -> bytes:
    url = f"{MD_URL}/{model_urn}/manifest/{quote(derivative_urn, safe='')}"
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=180,
    )
    response.raise_for_status()
    return response.content


def list_f2d_viewables(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Return 2D geometry viewables with their f2d graphics resource URNs."""
    views: list[dict[str, Any]] = []
    for node in _iter_manifest_nodes(manifest):
        if node.get("type") != "geometry" or node.get("role") != "2d":
            continue
        view_guid = node.get("guid")
        view_name = node.get("name") or "Unnamed view"
        f2d_urn = None
        for child in _iter_manifest_nodes(node):
            if child.get("mime") == "application/autodesk-f2d" and child.get("urn"):
                f2d_urn = str(child["urn"])
                break
        if view_guid and f2d_urn:
            views.append({"guid": view_guid, "name": view_name, "f2d_urn": f2d_urn})
    return views


def find_property_database_urn(manifest: dict[str, Any]) -> str | None:
    for node in _iter_manifest_nodes(manifest):
        mime = str(node.get("mime") or "")
        if "propertydatabase" in mime.lower() or mime == "application/autodesk-db":
            urn = node.get("urn")
            if urn:
                return str(urn)
    return None


def download_property_database(
    token: str | dict[str, Any],
    model_urn: str,
    *,
    cache_path: Path | None = None,
) -> Path:
    access = _resolve_token(token)
    manifest = get_manifest(token, model_urn)
    if not manifest:
        raise RuntimeError(f"No manifest for URN {model_urn[:24]}")
    db_urn = find_property_database_urn(manifest)
    if not db_urn:
        raise RuntimeError("PropertyDatabase not found in manifest")
    if cache_path and cache_path.is_file():
        return cache_path
    payload = _download_derivative(access, model_urn, db_urn)
    target = cache_path or Path(tempfile.gettempdir()) / f"aps_props_{model_urn[:12]}.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    logger.info("PropertyDatabase saved %s (%d bytes)", target, len(payload))
    return target


def query_dbid_layers(db_path: Path) -> dict[int, str]:
    """Map APS dbId (entity_id) → layer name from SQLite PropertyDatabase."""
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT id FROM _objects_attr WHERE lower(name)='layer' OR lower(display_name)='layer' LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            return {}
        layer_attr_id = int(row[0])
        cur.execute(
            """
            SELECT e.entity_id, v.value
            FROM _objects_eav e
            JOIN _objects_val v ON v.id = e.value_id
            WHERE e.attribute_id = ?
            """,
            (layer_attr_id,),
        )
        return {int(entity_id): str(value) for entity_id, value in cur.fetchall()}
    finally:
        con.close()


def query_dbid_names(db_path: Path) -> dict[int, str]:
    """Map APS dbId → entity/block name from PropertyDatabase."""
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT id FROM _objects_attr
            WHERE lower(name) IN ('name', 'type')
               OR lower(display_name) IN ('name', 'type')
            ORDER BY CASE WHEN lower(name) = 'name' THEN 0 ELSE 1 END
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            return {}
        attr_id = int(row[0])
        cur.execute(
            """
            SELECT e.entity_id, v.value
            FROM _objects_eav e
            JOIN _objects_val v ON v.id = e.value_id
            WHERE e.attribute_id = ?
            """,
            (attr_id,),
        )
        return {int(entity_id): str(value) for entity_id, value in cur.fetchall()}
    finally:
        con.close()


def query_dbid_entity_types(db_path: Path) -> dict[int, str]:
    return query_dbid_names(db_path)
