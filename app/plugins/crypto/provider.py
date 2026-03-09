"""CoinGecko-based cryptocurrency data provider (BTC, ETH, …).

Free tier: no API key needed; rate limit ≈ 10–30 req/min.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger

from app.providers import BaseDataProvider, PricePoint


class CryptoProvider(BaseDataProvider):
    """Fetches crypto prices from the CoinGecko REST API."""

    PROVIDER_KEY = "crypto_coingecko"

    _COIN_MAP: dict[str, str] = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "BNB": "binancecoin",
        "XRP": "ripple",
        "DOGE": "dogecoin",
        "ADA": "cardano",
        "AVAX": "avalanche-2",
        "DOT": "polkadot",
        "MATIC": "matic-network",
    }

    def __init__(self, base_url: str = "", api_key: str = "", **kw: Any) -> None:
        super().__init__(base_url or "https://api.coingecko.com/api/v3", api_key, **kw)
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30)

    # ── helpers ───────────────────────────────────────────────────────

    def _resolve_id(self, symbol: str) -> str:
        return self._COIN_MAP.get(symbol.upper(), symbol.lower())

    # ── interface implementation ──────────────────────────────────────

    async def fetch_latest(self, symbols: list[str]) -> list[PricePoint]:
        ids = ",".join(self._resolve_id(s) for s in symbols)
        resp = await self._client.get(
            "/simple/price",
            params={
                "ids": ids,
                "vs_currencies": "usd",
                "include_24hr_vol": "true",
                "include_24hr_change": "true",
                "include_last_updated_at": "true",
            },
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        points: list[PricePoint] = []
        for sym in symbols:
            cg_id = self._resolve_id(sym)
            info = data.get(cg_id, {})
            if not info:
                logger.warning("CoinGecko returned no data for {}", cg_id)
                continue
            ts = datetime.fromtimestamp(info.get("last_updated_at", 0), tz=timezone.utc)
            points.append(
                PricePoint(
                    symbol=sym.upper(),
                    timestamp=ts,
                    close=info.get("usd", 0),
                    volume=info.get("usd_24h_vol"),
                    extra={"change_24h_pct": info.get("usd_24h_change")},
                )
            )
        return points

    async def fetch_history(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[PricePoint]:
        cg_id = self._resolve_id(symbol)
        resp = await self._client.get(
            f"/coins/{cg_id}/market_chart/range",
            params={
                "vs_currency": "usd",
                "from": int(start.timestamp()),
                "to": int(end.timestamp()),
            },
        )
        resp.raise_for_status()
        data = resp.json()

        points: list[PricePoint] = []
        prices = data.get("prices", [])
        volumes = data.get("total_volumes", [])
        vol_map = {int(v[0]): v[1] for v in volumes} if volumes else {}

        for ts_ms, price in prices:
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            points.append(
                PricePoint(
                    symbol=symbol.upper(),
                    timestamp=ts,
                    close=price,
                    volume=vol_map.get(int(ts_ms)),
                )
            )
        return points

    async def health_check(self) -> bool:
        try:
            r = await self._client.get("/ping")
            return r.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
