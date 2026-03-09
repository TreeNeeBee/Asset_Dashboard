"""Stooq-based stock data provider — completely free, no API key needed.

Endpoints
---------
* Quote (JSON):   https://stooq.com/q/l/?s=aapl.us+msft.us&f=sd2t2ohlcv&h&e=json
* History (CSV):  https://stooq.com/q/d/l/?s=aapl.us&d1=20240101&d2=20240201&i=d

Supports batch quotes in a single HTTP request.  No rate-limit / key required.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger

from app.providers import BaseDataProvider, PricePoint


class StockProvider(BaseDataProvider):
    """Fetches stock prices from the Stooq free API."""

    PROVIDER_KEY = "stock_stooq"

    # Stooq uses  .US  suffix for US equities
    _SUFFIX = ".US"

    def __init__(self, base_url: str = "", api_key: str = "", **kw: Any) -> None:
        super().__init__(base_url or "https://stooq.com", api_key, **kw)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30,
            headers={"User-Agent": "AssetDashboard/2.0"},
        )

    # ── helpers ───────────────────────────────────────────────────

    def _stooq_symbol(self, symbol: str) -> str:
        """AAPL → aapl.us"""
        s = symbol.upper()
        if s.endswith(self._SUFFIX):
            return s.lower()
        return f"{s.lower()}{self._SUFFIX.lower()}"

    @staticmethod
    def _plain_symbol(stooq_sym: str) -> str:
        """AAPL.US → AAPL"""
        return stooq_sym.split(".")[0].upper()

    # ── interface implementation ──────────────────────────────────

    async def fetch_latest(self, symbols: list[str]) -> list[PricePoint]:
        # Batch query:  s=aapl.us+msft.us+…
        # NOTE: The "+" separator is literal in Stooq's API, but httpx encodes
        # it as %2B when passed via params dict.  Build the URL manually.
        ids = "+".join(self._stooq_symbol(s) for s in symbols)
        url = f"/q/l/?s={ids}&f=sd2t2ohlcv&h&e=json"
        resp = await self._client.get(url)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("symbols", [])
        if not items:
            logger.warning("Stooq returned no data for {}", ids)
            return []

        points: list[PricePoint] = []
        for item in items:
            sym = self._plain_symbol(item.get("symbol", ""))
            close_val = item.get("close")
            if close_val is None:
                logger.warning("Stooq: no close price for {}", sym)
                continue

            # Parse date + time
            date_str = item.get("date", "")
            time_str = item.get("time", "00:00:00")
            try:
                ts = datetime.strptime(
                    f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)

            points.append(
                PricePoint(
                    symbol=sym,
                    timestamp=ts,
                    open=item.get("open"),
                    high=item.get("high"),
                    low=item.get("low"),
                    close=float(close_val),
                    volume=item.get("volume"),
                )
            )
        return points

    async def fetch_history(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[PricePoint]:
        stooq_sym = self._stooq_symbol(symbol)
        d1 = start.strftime("%Y%m%d")
        d2 = end.strftime("%Y%m%d")

        resp = await self._client.get(
            "/q/d/l/",
            params={"s": stooq_sym, "d1": d1, "d2": d2, "i": "d"},
        )
        resp.raise_for_status()
        text = resp.text.strip()
        if not text or "No data" in text:
            logger.info("Stooq: no history for {} in [{}, {}]", symbol, d1, d2)
            return []

        reader = csv.DictReader(io.StringIO(text))
        points: list[PricePoint] = []
        plain = symbol.split(".")[0].upper()
        for row in reader:
            try:
                dt = datetime.strptime(row["Date"], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except (KeyError, ValueError):
                continue
            points.append(
                PricePoint(
                    symbol=plain,
                    timestamp=dt,
                    open=_f(row.get("Open")),
                    high=_f(row.get("High")),
                    low=_f(row.get("Low")),
                    close=_f(row.get("Close")) or 0,
                    volume=_f(row.get("Volume")),
                )
            )
        points.sort(key=lambda p: p.timestamp)
        return points

    async def health_check(self) -> bool:
        try:
            r = await self._client.get(
                "/q/l/",
                params={"s": "aapl.us", "f": "sc", "h": "", "e": "json"},
            )
            return r.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()


def _f(val: Any) -> float | None:
    """Safely cast to float."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
