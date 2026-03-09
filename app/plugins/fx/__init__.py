"""Foreign Exchange plugin — ViewModel (MVVM).

Binds the FX Model (ExchangeRate-API provider + seed data) with the
FX View (Grafana panels) and manages fetch-interval configuration.

All settings are read from ``config.yaml`` next to this file.
"""

from __future__ import annotations

from pathlib import Path

from app.models import SourceCategory
from app.plugins import BasePlugin, IntervalConfig, PluginConfig
from app.plugins.fx.model import FxModel
from app.plugins.fx.view import FxView

_CONFIG_PATH = Path(__file__).parent / "config.yaml"


class FxPlugin(BasePlugin):
    """ViewModel for foreign-exchange rate tracking."""

    def __init__(self) -> None:
        cfg = PluginConfig(_CONFIG_PATH)
        super().__init__(
            model=FxModel(config=cfg),
            view=FxView(),
            interval=IntervalConfig(fetch_interval_ms=120_000),
            config=cfg,
        )

    # ── metadata ──────────────────────────────────────────────────
    @property
    def key(self) -> str:
        return "fx"

    @property
    def name(self) -> str:
        return "Foreign Exchange"

    @property
    def description(self) -> str:
        return "Foreign exchange rates via ExchangeRate-API (USD/CNY, EUR/USD …)"

    @property
    def category(self) -> SourceCategory:
        return SourceCategory.FX


# Module-level instance — discovered by PluginManager
plugin = FxPlugin()
