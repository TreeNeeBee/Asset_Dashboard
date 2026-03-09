"""Foreign-exchange rate provider using the free ExchangeRate-API.

Endpoint: https://open.er-api.com/v6/latest/{BASE}
No API key required for the free tier.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger

from app.providers import BaseDataProvider, PricePoint


class FxProvider(BaseDataProvider):
    """Fetches live FX rates (e.g. USD/CNY, EUR/USD)."""

    PROVIDER_KEY = "fx_exchange_rate"

    def __init__(self, base_url: str = "", api_key: str = "", **kw: Any) -> None:
        super().__init__(base_url or "https://open.er-api.com/v6", api_key, **kw)
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30)

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_pair(symbol: str) -> tuple[str, str]:
        """Parse 'USD/CNY' or 'USDCNY' into (base, quote)."""
        if "/" in symbol:
            parts = symbol.split("/")
            return parts[0].upper(), parts[1].upper()
        if len(symbol) == 6:
            return symbol[:3].upper(), symbol[3:].upper()
        raise ValueError(f"Cannot parse FX pair: {symbol}")

    # ── interface implementation ──────────────────────────────────────

    async def fetch_latest(self, symbols: list[str]) -> list[PricePoint]:
        # Group by base currency to minimise HTTP calls
        bases: dict[str, list[str]] = {}
        pair_map: dict[str, tuple[str, str]] = {}
        for sym in symbols:
            base, quote = self._parse_pair(sym)
            bases.setdefault(base, []).append(quote)
            pair_map[sym] = (base, quote)

        rate_cache: dict[str, dict[str, float]] = {}
        for base in bases:
            resp = await self._client.get(f"/latest/{base}")
            resp.raise_for_status()
            body = resp.json()
            rate_cache[base] = body.get("rates", {})

        points: list[PricePoint] = []
        now = datetime.now(timezone.utc)
        for sym in symbols:
            base, quote = pair_map[sym]
            rate = rate_cache.get(base, {}).get(quote)
            if rate is None:
                logger.warning("No FX rate found for {}/{}", base, quote)
                continue
            points.append(
                PricePoint(
                    symbol=f"{base}/{quote}",
                    timestamp=now,
                    close=rate,
                )
            )
        return points

    async def fetch_history(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[PricePoint]:
        """The free tier has no historical endpoint — return empty list."""
        logger.info("FX history not available on free tier for {}", symbol)
        return []

    async def health_check(self) -> bool:
        try:
            r = await self._client.get("/latest/USD")
            return r.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
