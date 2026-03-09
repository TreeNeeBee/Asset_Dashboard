"""Crypto plugin — Model layer (data provider + seed data)."""

from __future__ import annotations

from typing import Any

from app.plugins import BasePluginModel, PluginConfig
from app.plugins.crypto.provider import CryptoProvider
from app.providers import BaseDataProvider


class CryptoModel(BasePluginModel):
    """Data layer: CoinGecko provider and default crypto assets."""

    def __init__(self, config: PluginConfig | None = None) -> None:
        super().__init__(config)

    def provider_class(self) -> type[BaseDataProvider]:
        return CryptoProvider

    def default_source(self) -> dict[str, Any]:
        if self._config and self._config.source:
            return dict(self._config.source)
        return {
            "name": "CoinGecko Crypto",
            "provider": CryptoProvider.PROVIDER_KEY,
            "base_url": "https://api.coingecko.com/api/v3",
            "description": "Cryptocurrency prices via CoinGecko free API",
        }

    def default_assets(self) -> list[dict[str, str]]:
        if self._config and self._config.assets:
            return self._config.assets
        return [
            {"symbol": "BTC", "display_name": "Bitcoin"},
            {"symbol": "ETH", "display_name": "Ethereum"},
            {"symbol": "SOL", "display_name": "Solana"},
        ]
