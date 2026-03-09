"""Grafana dashboard JSON-model builder & provisioning helpers.

Dynamically generates a Grafana dashboard from all loaded plugins.
Each plugin contributes its own panel definitions via ``grafana_panels()``.

The generated JSON is written to disk so Grafana's file-provisioner can
pick it up, and can also be pushed via the Grafana HTTP API at runtime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.plugins import (
    API_BASE_URL,
    INFINITY_DATASOURCE,
    GrafanaPanelDef,
    plugin_manager,
)

DASHBOARD_UID = "asset_dashboard_main"


# ────────────────────────────────────────────────────────────────────
# Convert a GrafanaPanelDef → raw Grafana JSON panel dict
# ────────────────────────────────────────────────────────────────────

def _panel_def_to_json(
    pdef: GrafanaPanelDef,
    panel_id: int,
    grid_x: int,
    grid_y: int,
) -> dict[str, Any]:
    """Translate a plugin-supplied :class:`GrafanaPanelDef` into Grafana JSON."""
    url = f"{API_BASE_URL}{pdef.url_path}"
    panel: dict[str, Any] = {
        "id": panel_id,
        "type": pdef.panel_type,
        "title": pdef.title,
        "datasource": INFINITY_DATASOURCE,
        "gridPos": {"h": pdef.height, "w": pdef.width, "x": grid_x, "y": grid_y},
        "targets": [
            {
                "refId": "A",
                "datasource": INFINITY_DATASOURCE,
                "type": "json",
                "parser": "backend",
                "source": "url",
                "url": url,
                "url_options": {"method": "GET"},
                "root_selector": pdef.root_selector,
                "columns": pdef.columns,
            }
        ],
    }
    if pdef.field_config:
        panel["fieldConfig"] = pdef.field_config
    return panel


# ────────────────────────────────────────────────────────────────────
# Global "overview" panels (not plugin-specific)
# ────────────────────────────────────────────────────────────────────

def _overview_panels(start_id: int, start_y: int) -> tuple[list[dict], int, int]:
    """Return the overview row: all-prices table + stat panels.

    Returns ``(panels, next_id, next_y)`` so callers can chain.
    """
    panels: list[dict] = []

    # All-prices table
    panels.append({
        "id": start_id,
        "type": "table",
        "title": "Latest Prices (All Assets)",
        "datasource": INFINITY_DATASOURCE,
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": start_y},
        "targets": [{
            "refId": "A",
            "datasource": INFINITY_DATASOURCE,
            "type": "json",
            "parser": "backend",
            "source": "url",
            "url": f"{API_BASE_URL}/api/v1/prices?size=50",
            "url_options": {"method": "GET"},
            "root_selector": "items",
            "columns": [
                {"selector": "asset_id", "text": "Asset ID", "type": "number"},
                {"selector": "timestamp", "text": "Time", "type": "timestamp"},
                {"selector": "open", "text": "Open", "type": "number"},
                {"selector": "high", "text": "High", "type": "number"},
                {"selector": "low", "text": "Low", "type": "number"},
                {"selector": "close", "text": "Close", "type": "number"},
                {"selector": "volume", "text": "Volume", "type": "number"},
            ],
        }],
    })

    # Source count
    panels.append({
        "id": start_id + 1,
        "type": "stat",
        "title": "Source Count",
        "datasource": INFINITY_DATASOURCE,
        "gridPos": {"h": 4, "w": 6, "x": 0, "y": start_y + 8},
        "targets": [{
            "refId": "A",
            "datasource": INFINITY_DATASOURCE,
            "type": "json",
            "parser": "backend",
            "source": "url",
            "url": f"{API_BASE_URL}/api/v1/sources?size=1",
            "url_options": {"method": "GET"},
            "root_selector": "",
            "columns": [{"selector": "total", "text": "Sources", "type": "number"}],
        }],
    })

    # Asset count
    panels.append({
        "id": start_id + 2,
        "type": "stat",
        "title": "Asset Count",
        "datasource": INFINITY_DATASOURCE,
        "gridPos": {"h": 4, "w": 6, "x": 6, "y": start_y + 8},
        "targets": [{
            "refId": "A",
            "datasource": INFINITY_DATASOURCE,
            "type": "json",
            "parser": "backend",
            "source": "url",
            "url": f"{API_BASE_URL}/api/v1/assets?size=1",
            "url_options": {"method": "GET"},
            "root_selector": "",
            "columns": [{"selector": "total", "text": "Assets", "type": "number"}],
        }],
    })

    # Plugin count
    panels.append({
        "id": start_id + 3,
        "type": "stat",
        "title": "Loaded Plugins",
        "datasource": INFINITY_DATASOURCE,
        "gridPos": {"h": 4, "w": 6, "x": 12, "y": start_y + 8},
        "targets": [{
            "refId": "A",
            "datasource": INFINITY_DATASOURCE,
            "type": "json",
            "parser": "backend",
            "source": "url",
            "url": f"{API_BASE_URL}/api/v1/plugins",
            "url_options": {"method": "GET"},
            "root_selector": "",
            "columns": [{"selector": "total", "text": "Plugins", "type": "number"}],
        }],
    })

    return panels, start_id + 4, start_y + 12


# ────────────────────────────────────────────────────────────────────
# Build full dashboard from loaded plugins
# ────────────────────────────────────────────────────────────────────

def build_dashboard_model(
    source_map: dict[str, int] | None = None,
    asset_map: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    """Return the full Grafana dashboard JSON model.

    Parameters
    ----------
    source_map : {plugin_key: source_id}
    asset_map  : {plugin_key: {symbol: asset_id}}

    If not provided, empty maps are used (panels will have dummy ids).
    """
    source_map = source_map or {}
    asset_map = asset_map or {}

    all_panels: list[dict] = []
    panel_id = 1
    cursor_y = 0

    # ― overview section ―
    overview, panel_id, cursor_y = _overview_panels(panel_id, cursor_y)
    all_panels.extend(overview)

    # ― per-plugin sections ―
    plugins = plugin_manager.all_plugins()
    tags = ["asset"]
    for plug in plugins:
        tags.append(plug.key)
        src_id = source_map.get(plug.key, 0)
        am = asset_map.get(plug.key, {})

        pdefs = plug.grafana_panels(src_id, am)
        if not pdefs:
            continue

        # Row header
        all_panels.append({
            "id": panel_id,
            "type": "row",
            "title": plug.name,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": cursor_y},
            "collapsed": False,
            "panels": [],
        })
        panel_id += 1
        cursor_y += 1

        col_x = 0
        row_max_h = 0
        for pdef in pdefs:
            if col_x + pdef.width > 24:
                cursor_y += row_max_h
                col_x = 0
                row_max_h = 0
            all_panels.append(_panel_def_to_json(pdef, panel_id, col_x, cursor_y))
            panel_id += 1
            col_x += pdef.width
            row_max_h = max(row_max_h, pdef.height)

        cursor_y += row_max_h

    return {
        "uid": DASHBOARD_UID,
        "title": "Asset Dashboard",
        "tags": tags,
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "refresh": "5s",
        "time": {"from": "now-7d", "to": "now"},
        "panels": all_panels,
    }


# ────────────────────────────────────────────────────────────────────
# Export to disk (for file-based provisioning)
# ────────────────────────────────────────────────────────────────────

def export_dashboard_json(
    source_map: dict[str, int] | None = None,
    asset_map: dict[str, dict[str, int]] | None = None,
    output_dir: str | Path = "grafana/dashboards",
) -> Path:
    """Write dashboard JSON to disk for Grafana file provisioning."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fpath = out / "asset_dashboard.json"
    model = build_dashboard_model(source_map, asset_map)
    fpath.write_text(json.dumps(model, indent=2))
    logger.info("Exported Grafana dashboard → {}", fpath)
    return fpath
