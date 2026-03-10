"""Declarative plugin support — create plugins from config.yaml + provider class.

For simple plugins that follow the standard pattern (time-series panels,
config-driven source/assets), use :func:`create_plugin` to eliminate all
boilerplate::

    # app/plugins/crypto/__init__.py
    from app.plugins.defaults import create_plugin
    from .provider import CryptoProvider

    plugin = create_plugin(__file__, CryptoProvider)

For advanced cases, pass custom ``model`` or ``view`` instances to override
the defaults while still benefiting from config-driven metadata.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from app.models import SourceCategory
from app.providers import BaseDataProvider

from .base import (
    BasePlugin,
    BasePluginModel,
    BasePluginView,
    GrafanaPanelDef,
)
from .config import PluginConfig


# ────────────────────────────────────────────────────────────────────
# DefaultPluginModel — config-driven, no custom code needed
# ────────────────────────────────────────────────────────────────────

class DefaultPluginModel(BasePluginModel):
    """Config-driven Model — reads source and assets from ``config.yaml``.

    Only the provider class must be supplied; everything else is derived
    from the YAML configuration file.
    """

    def __init__(
        self,
        provider_cls: type[BaseDataProvider],
        config: PluginConfig | None = None,
    ) -> None:
        super().__init__(config)
        self._provider_cls = provider_cls

    def provider_class(self) -> type[BaseDataProvider]:
        return self._provider_cls

    def default_source(self) -> dict[str, Any]:
        if self._config and self._config.source:
            return dict(self._config.source)
        # Minimal fallback built from provider key
        return {
            "name": self._provider_cls.PROVIDER_KEY,
            "provider": self._provider_cls.PROVIDER_KEY,
        }

    def default_assets(self) -> list[dict[str, str]]:
        if self._config and self._config.assets:
            return self._config.assets
        return []


# ────────────────────────────────────────────────────────────────────
# DefaultPluginView — config-driven standard time-series panels
# ────────────────────────────────────────────────────────────────────

class DefaultPluginView(BasePluginView):
    """Config-driven View — generates standard time-series panels.

    Panel title prefix and close-column label are read from ``config.yaml``
    (``panel_title_prefix`` / ``close_column_label``).
    """

    def __init__(self, config: PluginConfig | None = None) -> None:
        self._config = config

    def grafana_panels(
        self, source_id: int, asset_map: dict[str, int]
    ) -> list[GrafanaPanelDef]:
        prefix = self._config.panel_title_prefix if self._config else ""
        label = self._config.close_column_label if self._config else "Close"

        # Build symbol → display_name / groups lookups from config
        display_map: dict[str, str] = {}
        groups_map: dict[str, list[str]] = {}
        if self._config and self._config.assets:
            for a in self._config.assets:
                display_map[a["symbol"]] = a.get("display_name", a["symbol"])
                groups_map[a["symbol"]] = a.get("groups", [])

        panels: list[GrafanaPanelDef] = []
        for symbol, asset_id in asset_map.items():
            display = display_map.get(symbol, symbol)
            panels.append(
                GrafanaPanelDef(
                    panel_type="timeseries",
                    title=f"{prefix} — {display}",
                    width=12,
                    height=8,
                    url_path=f"/api/v1/prices?asset_id={asset_id}&size=500",
                    root_selector="items",
                    columns=[
                        {"selector": "timestamp", "text": "Time", "type": "timestamp"},
                        {"selector": "close", "text": label, "type": "number"},
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
                    groups=groups_map.get(symbol, []),
                )
            )
        return panels


# ────────────────────────────────────────────────────────────────────
# DeclarativePlugin — ViewModel assembled entirely from config + provider
# ────────────────────────────────────────────────────────────────────

class DeclarativePlugin(BasePlugin):
    """Plugin fully described by ``config.yaml`` metadata + a provider class.

    Metadata properties (``key``, ``name``, ``category``, …) are read
    from the YAML config instead of being hard-coded in Python.
    """

    def __init__(
        self,
        config: PluginConfig,
        provider_cls: type[BaseDataProvider],
        *,
        model: BasePluginModel | None = None,
        view: BasePluginView | None = None,
    ) -> None:
        super().__init__(
            model=model or DefaultPluginModel(provider_cls, config=config),
            view=view or DefaultPluginView(config=config),
            config=config,
        )
        self._provider_cls = provider_cls

    @property
    def key(self) -> str:
        return self._config.key  # type: ignore[union-attr]

    @property
    def name(self) -> str:
        return self._config.plugin_name  # type: ignore[union-attr]

    @property
    def description(self) -> str:
        return self._config.description  # type: ignore[union-attr]

    @property
    def version(self) -> str:
        return self._config.version  # type: ignore[union-attr]

    @property
    def category(self) -> SourceCategory:
        return SourceCategory(self._config.category)  # type: ignore[union-attr]


# ────────────────────────────────────────────────────────────────────
# Factory function
# ────────────────────────────────────────────────────────────────────

def create_plugin(
    init_file: str,
    provider_class: type[BaseDataProvider],
    *,
    model: BasePluginModel | None = None,
    view: BasePluginView | None = None,
) -> DeclarativePlugin:
    """Create a plugin from the ``config.yaml`` next to *init_file*.

    Usage in a plugin's ``__init__.py``::

        from app.plugins.defaults import create_plugin
        from .provider import MyProvider

        plugin = create_plugin(__file__, MyProvider)

    Pass *model* or *view* to override the config-driven defaults.
    """
    cfg_path = Path(init_file).parent / "config.yaml"
    cfg = PluginConfig(cfg_path)
    return DeclarativePlugin(cfg, provider_class, model=model, view=view)
