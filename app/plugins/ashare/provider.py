"""Sina Finance–based A-share (China) data provider.

Endpoint
--------
* Real-time quote: ``https://hq.sinajs.cn/list=sh000001,sz399001,...``

Symbols in config use Yahoo Finance conventions (``000001.SS``, ``399001.SZ``).
The provider converts them to Sina codes internally (``sh000001``, ``sz399001``).

Free, no auth/key, supports batch queries, GBK-encoded response.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger

from app.providers import BaseDataProvider, PricePoint

# Regex to parse Sina response lines:
# var hq_str_sh000001="上证指数,3219.09,3218.05,3224.12,...";
_LINE_RE = re.compile(r'var hq_str_(\w+)="([^"]*)"')


class AShareProvider(BaseDataProvider):
    """Fetches A-share prices from Sina Finance."""

    PROVIDER_KEY = "ashare_sina"

    def __init__(self, base_url: str = "", api_key: str = "", **kw: Any) -> None:
        super().__init__(base_url or "https://hq.sinajs.cn", api_key, **kw)
        self._client = httpx.AsyncClient(
            timeout=30,
            headers={
                "Referer": "https://finance.sina.com.cn",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            },
        )

    # ── symbol conversion ─────────────────────────────────────────

    @staticmethod
    def _to_sina_code(symbol: str) -> str:
        """Convert Yahoo-style symbol to Sina code.

        ``000001.SS`` → ``sh000001``
        ``399001.SZ`` → ``sz399001``
        """
        if "." not in symbol:
            return symbol.lower()
        code, suffix = symbol.rsplit(".", 1)
        prefix = "sh" if suffix.upper() == "SS" else "sz"
        return f"{prefix}{code}"

    @staticmethod
    def _from_sina_code(sina_code: str) -> str:
        """Convert Sina code back to Yahoo-style.

        ``sh000001`` → ``000001.SS``
        ``sz399001`` → ``399001.SZ``
        """
        prefix = sina_code[:2]
        code = sina_code[2:]
        suffix = "SS" if prefix == "sh" else "SZ"
        return f"{code}.{suffix}"

    # ── response parsing ──────────────────────────────────────────

    @staticmethod
    def _parse_response(text: str) -> dict[str, list[str]]:
        """Parse Sina response into ``{sina_code: [field, ...]}``."""
        result: dict[str, list[str]] = {}
        for match in _LINE_RE.finditer(text):
            sina_code, csv_str = match.group(1), match.group(2)
            if csv_str:
                result[sina_code] = csv_str.split(",")
        return result

    # ── Sina CSV field indices ────────────────────────────────────
    #  0: 名称 (name)
    #  1: 今开 (open)
    #  2: 昨收 (prev close)
    #  3: 当前价 (current price / close)
    #  4: 最高 (high)
    #  5: 最低 (low)
    #  6: 买一 (bid)
    #  7: 卖一 (ask)
    #  8: 成交量 (volume, unit varies)
    #  9: 成交额 (turnover)
    # 30: 日期 (YYYY-MM-DD)
    # 31: 时间 (HH:MM:SS)

    IDX_OPEN = 1
    IDX_CLOSE = 3
    IDX_HIGH = 4
    IDX_LOW = 5
    IDX_VOLUME = 8
    IDX_DATE = 30
    IDX_TIME = 31

    # ── interface implementation ──────────────────────────────────

    async def fetch_latest(self, symbols: list[str]) -> list[PricePoint]:
        """Fetch latest prices — single batch request for all symbols."""
        sina_codes = [self._to_sina_code(s) for s in symbols]
        code_list = ",".join(sina_codes)
        url = f"{self.base_url}/list={code_list}"

        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            text = resp.content.decode("gbk", errors="replace")
        except Exception:
            logger.exception("Sina Finance request failed")
            return []

        parsed = self._parse_response(text)

        points: list[PricePoint] = []
        for sym in symbols:
            sina_code = self._to_sina_code(sym)
            fields = parsed.get(sina_code)
            if not fields or len(fields) < 32:
                logger.warning("Sina: no data for {} ({})", sym, sina_code)
                continue

            try:
                close_val = float(fields[self.IDX_CLOSE])
                if close_val == 0:
                    logger.warning("Sina: zero price for {} — market closed?", sym)
                    continue

                # Parse timestamp
                date_str = fields[self.IDX_DATE].strip()
                time_str = fields[self.IDX_TIME].strip()
                try:
                    ts = datetime.strptime(
                        f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=timezone.utc)
                except (ValueError, IndexError):
                    ts = datetime.now(timezone.utc)

                open_val = float(fields[self.IDX_OPEN]) or None
                high_val = float(fields[self.IDX_HIGH]) or None
                low_val = float(fields[self.IDX_LOW]) or None
                vol_val = float(fields[self.IDX_VOLUME]) if fields[self.IDX_VOLUME] else None

                points.append(
                    PricePoint(
                        symbol=sym,
                        timestamp=ts,
                        open=open_val,
                        high=high_val,
                        low=low_val,
                        close=close_val,
                        volume=vol_val,
                    )
                )
            except (ValueError, IndexError) as exc:
                logger.warning("Sina: failed to parse {} — {}", sym, exc)
                continue

        return points

    async def fetch_history(
        self, symbol: str, start: datetime, end: datetime,
    ) -> list[PricePoint]:
        """Fetch historical data — not supported by Sina real-time API."""
        return []

    async def close(self) -> None:
        await self._client.aclose()

