"""East Money (东方财富) US stock data provider — free, no API key needed.

Endpoints
---------
* Batch quote:  https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=105.AAPL,...
* History:      https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=105.AAPL&...

Supports batch real-time quotes in a single HTTP request.
No rate-limit / key required.  Works from mainland China.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

import httpx
from loguru import logger

from app.providers import BaseDataProvider, PricePoint


# East Money market code for US stocks (NASDAQ + NYSE)
_US_MARKET = 105

# US Eastern timezone — East Money timestamps align with US market hours
_US_EASTERN = ZoneInfo("America/New_York")

# ── Quote field mapping ───────────────────────────────────────────
# f2:  latest price      f5:  volume           f12: symbol
# f14: name (Chinese)    f15: high             f16: low
# f17: open              f18: previous close
_QUOTE_FIELDS = "f2,f5,f12,f14,f15,f16,f17,f18"

# ── Kline field mapping ──────────────────────────────────────────
# fields2 → f51:date, f52:open, f53:close, f54:high, f55:low,
#            f56:volume, f57:amount
_KLINE_FIELDS1 = "f1,f2,f3,f4,f5,f6"
_KLINE_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"


class StockProvider(BaseDataProvider):
    """Fetches US stock prices from East Money (东方财富) free API."""

    PROVIDER_KEY = "stock_eastmoney"

    def __init__(self, base_url: str = "", api_key: str = "", **kw: Any) -> None:
        super().__init__(
            base_url or "https://push2.eastmoney.com", api_key, **kw
        )
        self._quote_client = httpx.AsyncClient(
            base_url="https://push2.eastmoney.com",
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "AssetDashboard/2.0"},
        )
        self._hist_client = httpx.AsyncClient(
            base_url="https://push2his.eastmoney.com",
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "AssetDashboard/2.0"},
        )

    # ── helpers ───────────────────────────────────────────────────

    @staticmethod
    def _secid(symbol: str) -> str:
        """AAPL → 105.AAPL (East Money secid format for US stocks)."""
        sym = symbol.upper().split(".")[0]
        return f"{_US_MARKET}.{sym}"

    # ── interface implementation ──────────────────────────────────

    async def fetch_latest(self, symbols: list[str]) -> list[PricePoint]:
        """Batch quote — one HTTP call for all symbols."""
        secids = ",".join(self._secid(s) for s in symbols)
        resp = await self._quote_client.get(
            "/api/qt/ulist.np/get",
            params={"fltt": "2", "secids": secids, "fields": _QUOTE_FIELDS},
        )
        resp.raise_for_status()

        data = resp.json()
        if data.get("rc") != 0 or not data.get("data"):
            logger.warning("EastMoney batch quote failed: rc={}", data.get("rc"))
            return []

        items = data["data"].get("diff", [])
        now = datetime.now(_US_EASTERN)

        points: list[PricePoint] = []
        for item in items:
            sym = item.get("f12", "")
            close_val = item.get("f2")
            if close_val is None or close_val == "-":
                logger.warning("EastMoney: no price for {}", sym)
                continue

            points.append(
                PricePoint(
                    symbol=sym,
                    timestamp=now,
                    open=_f(item.get("f17")),
                    high=_f(item.get("f15")),
                    low=_f(item.get("f16")),
                    close=float(close_val),
                    volume=_f(item.get("f5")),
                )
            )
        return points

    async def fetch_history(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[PricePoint]:
        """Daily K-line history — clean JSON from East Money."""
        secid = self._secid(symbol)
        beg = start.strftime("%Y%m%d")
        end_s = end.strftime("%Y%m%d")

        resp = await self._hist_client.get(
            "/api/qt/stock/kline/get",
            params={
                "secid": secid,
                "fields1": _KLINE_FIELDS1,
                "fields2": _KLINE_FIELDS2,
                "klt": "101",       # daily
                "fqt": "0",         # no adjustment
                "beg": beg,
                "end": end_s,
                "lmt": "10000",     # max rows
            },
        )
        resp.raise_for_status()

        data = resp.json()
        if data.get("rc") != 0 or not data.get("data"):
            logger.info(
                "EastMoney: no history for {} in [{}, {}]", symbol, beg, end_s
            )
            return []

        klines = data["data"].get("klines", [])
        plain = symbol.split(".")[0].upper()

        points: list[PricePoint] = []
        for line in klines:
            # Format: "date,open,close,high,low,volume,amount,..."
            parts = line.split(",")
            if len(parts) < 7:
                continue
            try:
                dt = datetime.strptime(parts[0], "%Y-%m-%d").replace(
                    tzinfo=_US_EASTERN
                )
            except ValueError:
                continue

            points.append(
                PricePoint(
                    symbol=plain,
                    timestamp=dt,
                    open=_f(parts[1]),
                    high=_f(parts[3]),
                    low=_f(parts[4]),
                    close=_f(parts[2]) or 0,
                    volume=_f(parts[5]),
                )
            )
        points.sort(key=lambda p: p.timestamp)
        return points

    async def health_check(self) -> bool:
        try:
            r = await self._quote_client.get(
                "/api/qt/ulist.np/get",
                params={
                    "fltt": "2",
                    "secids": f"{_US_MARKET}.AAPL",
                    "fields": "f2,f12",
                },
            )
            return r.status_code == 200 and r.json().get("rc") == 0
        except Exception:
            return False

    async def close(self) -> None:
        await self._quote_client.aclose()
        await self._hist_client.aclose()


def _f(val: Any) -> float | None:
    """Safely cast to float."""
    if val is None or val == "-":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
