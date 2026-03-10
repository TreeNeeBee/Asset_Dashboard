"""Grafana dashboard JSON-model builder & provisioning helpers.

Dynamically generates Grafana dashboards from all loaded plugins.
Each plugin contributes its own panel definitions via ``grafana_panels()``.

**Tab / group support** — panels tagged with group names generate additional
dashboards.  The default "首页" tab contains *all* panels; each extra tab
contains only the panels assigned to that group.  Navigation links at the
top of every dashboard provide a tab-like switching experience.

The generated JSON files are written to disk so Grafana's file-provisioner
can pick them up, and can also be pushed via the Grafana HTTP API at runtime.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.plugins import (
    API_BASE_URL,
    BasePlugin,
    INFINITY_DATASOURCE,
    GrafanaPanelDef,
    plugin_manager,
)

DASHBOARD_UID = "asset_dashboard_main"
DEFAULT_TAB = "首页"


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
# Tab-navigation helpers
# ────────────────────────────────────────────────────────────────────

def _group_uid(group_name: str) -> str:
    """Stable, URL-safe UID for a group (tab) dashboard."""
    h = hashlib.md5(group_name.encode()).hexdigest()[:10]
    return f"asset_tab_{h}"


def _nav_links(extra_groups: set[str]) -> list[dict[str, Any]]:
    """Build tab-like navigation links for the dashboard top bar."""
    tabs = [DEFAULT_TAB] + sorted(extra_groups)
    links: list[dict[str, Any]] = []
    for tab in tabs:
        uid = DASHBOARD_UID if tab == DEFAULT_TAB else _group_uid(tab)
        links.append({
            "asDropdown": False,
            "icon": "dashboard",
            "includeVars": True,
            "keepTime": True,
            "tags": [],
            "targetBlank": False,
            "title": tab,
            "tooltip": "",
            "type": "link",
            "url": f"/d/{uid}",
        })
    return links


# ────────────────────────────────────────────────────────────────────
# Build a single dashboard
# ────────────────────────────────────────────────────────────────────

def _build_dashboard(
    uid: str,
    title: str,
    plugin_panels: list[tuple[BasePlugin, list[GrafanaPanelDef]]],
    *,
    group_filter: str | None = None,
    nav_links: list[dict[str, Any]] | None = None,
    tags: list[str] | None = None,
    include_overview: bool = True,
) -> dict[str, Any]:
    """Build a single Grafana dashboard JSON model.

    Parameters
    ----------
    group_filter
        ``None`` → include all panels (default / 首页 tab).
        A string → include only panels whose ``groups`` contains it.
    """
    tags = tags or ["asset"]
    all_panels: list[dict] = []
    panel_id = 1
    cursor_y = 0

    if include_overview:
        overview, panel_id, cursor_y = _overview_panels(panel_id, cursor_y)
        all_panels.extend(overview)

    for plug, pdefs in plugin_panels:
        # Filter panels when building a group tab
        if group_filter is not None:
            pdefs = [p for p in pdefs if group_filter in p.groups]

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

    model: dict[str, Any] = {
        "uid": uid,
        "title": title,
        "tags": tags,
        "timezone": "Asia/Shanghai",
        "schemaVersion": 39,
        "version": 1,
        "refresh": "1s",
        "time": {"from": "now-7d", "to": "now"},
        "timepicker": {
            "refresh_intervals": ["1s", "5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h", "2h", "1d"],
        },
        "panels": all_panels,
    }
    if nav_links:
        model["links"] = nav_links
    return model


# ────────────────────────────────────────────────────────────────────
# Multi-dashboard builder (main + group tabs)
# ────────────────────────────────────────────────────────────────────

def build_all_dashboards(
    source_map: dict[str, int] | None = None,
    asset_map: dict[str, dict[str, int]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build main dashboard + one per group tab.

    Returns ``{uid: dashboard_model, …}``.
    """
    source_map = source_map or {}
    asset_map = asset_map or {}

    # Collect panels from all plugins
    plugins = plugin_manager.all_plugins()
    plugin_panels: list[tuple[BasePlugin, list[GrafanaPanelDef]]] = []
    all_groups: set[str] = set()
    tags = ["asset"]

    for plug in plugins:
        tags.append(plug.key)
        src_id = source_map.get(plug.key, 0)
        am = asset_map.get(plug.key, {})
        pdefs = plug.grafana_panels(src_id, am)
        if pdefs:
            plugin_panels.append((plug, pdefs))
            for pdef in pdefs:
                all_groups.update(pdef.groups)

    # Build navigation links (only when extra groups exist)
    nav = _nav_links(all_groups) if all_groups else []

    dashboards: dict[str, dict[str, Any]] = {}

    # ── Default tab (首页): all panels ───────────────────────────
    dashboards[DASHBOARD_UID] = _build_dashboard(
        DASHBOARD_UID, "Asset Dashboard",
        plugin_panels,
        nav_links=nav, tags=tags, include_overview=True,
    )

    # ── Per-group tabs: filtered panels ──────────────────────────
    for group in sorted(all_groups):
        uid = _group_uid(group)
        dashboards[uid] = _build_dashboard(
            uid, f"Asset Dashboard — {group}",
            plugin_panels,
            group_filter=group, nav_links=nav, tags=tags,
            include_overview=False,
        )

    return dashboards


def build_dashboard_model(
    source_map: dict[str, int] | None = None,
    asset_map: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    """Return the main Grafana dashboard JSON model (backward compat)."""
    return build_all_dashboards(source_map, asset_map)[DASHBOARD_UID]


# ────────────────────────────────────────────────────────────────────
# Export to disk (for file-based provisioning)
# ────────────────────────────────────────────────────────────────────

def export_dashboard_json(
    source_map: dict[str, int] | None = None,
    asset_map: dict[str, dict[str, int]] | None = None,
    output_dir: str | Path = "grafana/dashboards",
) -> Path:
    """Write all dashboard JSON files to disk for Grafana file provisioning.

    The main dashboard is written to ``asset_dashboard.json``.
    Each group tab is written to ``asset_tab_<hash>.json``.
    Stale group files are cleaned up automatically.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Remove stale group dashboards from previous runs
    for old in out.glob("asset_tab_*.json"):
        old.unlink()

    dashboards = build_all_dashboards(source_map, asset_map)

    main_path = out / "asset_dashboard.json"
    for uid, model in dashboards.items():
        fpath = main_path if uid == DASHBOARD_UID else out / f"{uid}.json"
        fpath.write_text(json.dumps(model, indent=2))

    logger.info(
        "Exported {} Grafana dashboard(s) → {}",
        len(dashboards), out,
    )
    return main_path
