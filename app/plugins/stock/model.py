"""Stock plugin — Model layer (data provider + seed data)."""

from __future__ import annotations

from typing import Any

from app.plugins import BasePluginModel, PluginConfig
from app.plugins.stock.provider import StockProvider
from app.providers import BaseDataProvider


class StockModel(BasePluginModel):
    """Data layer: Stooq provider and default US stock assets."""

    def __init__(self, config: PluginConfig | None = None) -> None:
        super().__init__(config)

    def provider_class(self) -> type[BaseDataProvider]:
        return StockProvider

    def default_source(self) -> dict[str, Any]:
        if self._config and self._config.source:
            return dict(self._config.source)
        return {
            "name": "Stooq Stocks",
            "provider": StockProvider.PROVIDER_KEY,
            "base_url": "https://stooq.com",
            "api_key": "",
            "description": "US stock quotes via Stooq (free)",
        }

    def default_assets(self) -> list[dict[str, str]]:
        if self._config and self._config.assets:
            return self._config.assets
        return [
            {"symbol": "AAPL", "display_name": "Apple Inc."},
            {"symbol": "MSFT", "display_name": "Microsoft Corp."},
            {"symbol": "GOOGL", "display_name": "Alphabet Inc."},
            {"symbol": "TSLA", "display_name": "Tesla Inc."},
        ]
