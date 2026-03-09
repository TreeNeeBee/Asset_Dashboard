"""Cryptocurrency plugin — ViewModel (MVVM).

Binds the crypto Model (CoinGecko provider + seed data) with the
crypto View (Grafana panels) and manages fetch-interval configuration.

All settings are read from ``config.yaml`` next to this file.
"""

from __future__ import annotations

from pathlib import Path

from app.models import SourceCategory
from app.plugins import BasePlugin, IntervalConfig, PluginConfig
from app.plugins.crypto.model import CryptoModel
from app.plugins.crypto.view import CryptoView

_CONFIG_PATH = Path(__file__).parent / "config.yaml"


class CryptoPlugin(BasePlugin):
    """ViewModel for cryptocurrency tracking."""

    def __init__(self) -> None:
        cfg = PluginConfig(_CONFIG_PATH)
        super().__init__(
            model=CryptoModel(config=cfg),
            view=CryptoView(),
            interval=IntervalConfig(fetch_interval_ms=60_000),
            config=cfg,
        )

    # ── metadata ──────────────────────────────────────────────────
    @property
    def key(self) -> str:
        return "crypto"

    @property
    def name(self) -> str:
        return "Cryptocurrency"

    @property
    def description(self) -> str:
        return "Cryptocurrency prices via CoinGecko free API (BTC, ETH, SOL …)"

    @property
    def category(self) -> SourceCategory:
        return SourceCategory.CRYPTO


# Module-level instance — discovered by PluginManager
plugin = CryptoPlugin()
