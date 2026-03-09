"""Abstract data-source interface & provider registry.

Every concrete data provider (BTC, Stock, FX …) inherits from
``BaseDataProvider`` and is auto-registered via the ``ProviderRegistry``.

The design supports **dynamic add / remove** of providers at runtime, enabling
the dashboard to be extended without restarting the server.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Canonical data point returned by every provider
# ---------------------------------------------------------------------------

@dataclass
class PricePoint:
    """A single normalised price record produced by a provider."""
    symbol: str
    timestamp: datetime
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float = 0.0
    volume: Optional[float] = None
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class BaseDataProvider(abc.ABC):
    """Contract every data-source plugin must fulfil."""

    # Subclasses set this so the registry can match DB rows → code.
    PROVIDER_KEY: ClassVar[str] = ""

    def __init__(self, base_url: str = "", api_key: str = "", **kwargs: Any) -> None:
        self.base_url = base_url
        self.api_key = api_key

    # ── Mandatory interface ───────────────────────────────────────────
    @abc.abstractmethod
    async def fetch_latest(self, symbols: list[str]) -> list[PricePoint]:
        """Return the latest price(s) for the requested symbols."""
        ...

    @abc.abstractmethod
    async def fetch_history(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[PricePoint]:
        """Return historical OHLCV data for *symbol* in [start, end]."""
        ...

    # ── Optional lifecycle hooks ──────────────────────────────────────
    async def health_check(self) -> bool:
        """Return ``True`` if the upstream API is reachable."""
        return True

    async def close(self) -> None:
        """Cleanup resources (HTTP sessions, etc.)."""


# ---------------------------------------------------------------------------
# Provider registry (singleton)
# ---------------------------------------------------------------------------

class ProviderRegistry:
    """A thread-safe registry that maps *provider_key* → provider **class**.

    Usage::

        registry = ProviderRegistry()
        registry.register(MyCryptoProvider)          # add
        registry.unregister("crypto_coingecko")      # remove
        provider = registry.create("crypto_coingecko", base_url="…")
    """

    _instance: Optional["ProviderRegistry"] = None
    _providers: dict[str, type[BaseDataProvider]]

    def __new__(cls) -> "ProviderRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._providers = {}
        return cls._instance

    # ── Public API ────────────────────────────────────────────────────

    def register(self, provider_cls: type[BaseDataProvider]) -> None:
        key = provider_cls.PROVIDER_KEY
        if not key:
            raise ValueError(f"{provider_cls.__name__} has no PROVIDER_KEY set")
        self._providers[key] = provider_cls
        logger.info("Registered provider: {}", key)

    def unregister(self, key: str) -> None:
        removed = self._providers.pop(key, None)
        if removed:
            logger.info("Unregistered provider: {}", key)
        else:
            logger.warning("Provider key '{}' not found in registry", key)

    def create(self, key: str, **kwargs: Any) -> BaseDataProvider:
        """Instantiate a provider by its key, passing kwargs to __init__."""
        cls = self._providers.get(key)
        if cls is None:
            raise KeyError(f"No provider registered for key '{key}'. Available: {list(self._providers)}")
        return cls(**kwargs)

    def list_keys(self) -> list[str]:
        return list(self._providers.keys())

    def __contains__(self, key: str) -> bool:
        return key in self._providers

    def __repr__(self) -> str:
        return f"<ProviderRegistry providers={self.list_keys()}>"


# Module-level singleton for convenience
registry = ProviderRegistry()
