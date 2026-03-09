"""FX plugin — View layer (Grafana panel definitions)."""

from __future__ import annotations

from app.plugins import BasePluginView, GrafanaPanelDef


class FxView(BasePluginView):
    """Presentation layer: time-series charts for each tracked FX pair."""

    def grafana_panels(
        self, source_id: int, asset_map: dict[str, int]
    ) -> list[GrafanaPanelDef]:
        panels: list[GrafanaPanelDef] = []

        for symbol, asset_id in asset_map.items():
            panels.append(
                GrafanaPanelDef(
                    panel_type="timeseries",
                    title=f"FX — {symbol}",
                    width=12,
                    height=8,
                    url_path=f"/api/v1/prices?asset_id={asset_id}&size=500",
                    root_selector="items",
                    columns=[
                        {"selector": "timestamp", "text": "Time", "type": "timestamp"},
                        {"selector": "close", "text": "Rate", "type": "number"},
                    ],
                    field_config={
                        "defaults": {
                            "color": {"mode": "palette-classic"},
                            "custom": {
                                "drawStyle": "line",
                                "lineWidth": 2,
                                "fillOpacity": 10,
                            },
                        }
                    },
                )
            )

        return panels
