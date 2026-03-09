"""FX plugin — Model layer (data provider + seed data)."""

from __future__ import annotations

from typing import Any

from app.plugins import BasePluginModel, PluginConfig
from app.plugins.fx.provider import FxProvider
from app.providers import BaseDataProvider


class FxModel(BasePluginModel):
    """Data layer: ExchangeRate-API provider and default FX pairs."""

    def __init__(self, config: PluginConfig | None = None) -> None:
        super().__init__(config)

    def provider_class(self) -> type[BaseDataProvider]:
        return FxProvider

    def default_source(self) -> dict[str, Any]:
        if self._config and self._config.source:
            return dict(self._config.source)
        return {
            "name": "ExchangeRate FX",
            "provider": FxProvider.PROVIDER_KEY,
            "base_url": "https://open.er-api.com/v6",
            "description": "Foreign exchange rates via ExchangeRate-API",
        }

    def default_assets(self) -> list[dict[str, str]]:
        if self._config and self._config.assets:
            return self._config.assets
        return [
            {"symbol": "USD/CNY", "display_name": "US Dollar / Chinese Yuan"},
            {"symbol": "EUR/USD", "display_name": "Euro / US Dollar"},
            {"symbol": "GBP/USD", "display_name": "British Pound / US Dollar"},
            {"symbol": "USD/JPY", "display_name": "US Dollar / Japanese Yen"},
        ]
