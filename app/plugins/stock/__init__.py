"""US Stock plugin — ViewModel (MVVM).

Binds the stock Model (Stooq provider + seed data) with the
stock View (Grafana panels) and manages fetch-interval configuration.

All settings are read from ``config.yaml`` next to this file.
"""

from __future__ import annotations

from pathlib import Path

from app.models import SourceCategory
from app.plugins import BasePlugin, IntervalConfig, PluginConfig
from app.plugins.stock.model import StockModel
from app.plugins.stock.view import StockView

_CONFIG_PATH = Path(__file__).parent / "config.yaml"


class StockPlugin(BasePlugin):
    """ViewModel for US stock tracking."""

    def __init__(self) -> None:
        cfg = PluginConfig(_CONFIG_PATH)
        super().__init__(
            model=StockModel(config=cfg),
            view=StockView(),
            interval=IntervalConfig(fetch_interval_ms=300_000),
            config=cfg,
        )

    # ── metadata ──────────────────────────────────────────────────
    @property
    def key(self) -> str:
        return "stock"

    @property
    def name(self) -> str:
        return "US Stocks"

    @property
    def description(self) -> str:
        return "US stock quotes via Stooq (AAPL, MSFT, GOOGL, TSLA …)"

    @property
    def category(self) -> SourceCategory:
        return SourceCategory.STOCK


# Module-level instance — discovered by PluginManager
plugin = StockPlugin()
