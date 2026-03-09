"""End-to-end validation script for Asset Dashboard.

Run:  python -m tests.validate
(with API server running on localhost:8000)
"""

from __future__ import annotations

import asyncio
import sys

import httpx

BASE = "http://localhost:8000"
PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    tag = PASS if ok else FAIL
    print(f"  {tag}  {name}  {detail}")


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:

        # ── 1. Health ─────────────────────────────────────
        print("\n[1] Health check")
        r = await c.get("/health")
        record("GET /health", r.status_code == 200 and r.json().get("status") == "ok", f"status={r.status_code}")

        # ── 2. Sources CRUD ───────────────────────────────
        print("\n[2] DataSource CRUD")
        r = await c.get("/api/v1/sources")
        data = r.json()
        record("LIST sources", data["total"] >= 3, f"total={data['total']}")

        r = await c.get("/api/v1/sources/1")
        record("GET source/1", r.status_code == 200 and r.json()["name"] == "CoinGecko Crypto")

        r = await c.post("/api/v1/sources", json={
            "name": "Test Source",
            "category": "custom",
            "provider": "custom_test",
        })
        create_ok = r.status_code == 201
        test_src_id = r.json()["id"] if create_ok else -1
        record("CREATE source", create_ok, f"id={test_src_id}")

        if test_src_id > 0:
            r = await c.patch(f"/api/v1/sources/{test_src_id}", json={"description": "Testing"})
            record("UPDATE source", r.status_code == 200 and r.json().get("description") == "Testing")

            r = await c.delete(f"/api/v1/sources/{test_src_id}")
            record("DELETE source", r.status_code == 204)

            r = await c.get(f"/api/v1/sources/{test_src_id}")
            record("VERIFY source deleted", r.status_code == 404)
        else:
            record("UPDATE source", False, "skipped — create failed")
            record("DELETE source", False, "skipped — create failed")
            record("VERIFY source deleted", False, "skipped")

        # ── 3. Assets CRUD ────────────────────────────────
        print("\n[3] Asset CRUD")
        r = await c.get("/api/v1/assets")
        data = r.json()
        record("LIST assets", data["total"] >= 11, f"total={data['total']}")

        r = await c.post("/api/v1/assets", json={
            "source_id": 1,
            "symbol": "XRP",
            "display_name": "Ripple",
        })
        record("CREATE asset", r.status_code == 201, f"id={r.json().get('id')}")
        test_asset_id = r.json()["id"]

        r = await c.patch(f"/api/v1/assets/{test_asset_id}", json={"display_name": "Ripple (XRP)"})
        record("UPDATE asset", r.status_code == 200 and r.json()["display_name"] == "Ripple (XRP)")

        r = await c.delete(f"/api/v1/assets/{test_asset_id}")
        record("DELETE asset", r.status_code == 204)

        # ── 4. Price data ────────────────────────────────
        print("\n[4] Price records")
        r = await c.get("/api/v1/prices?size=5")
        data = r.json()
        record("LIST prices", data["total"] > 0, f"total={data['total']}")

        # filter by asset_id=1 (BTC)
        r = await c.get("/api/v1/prices?asset_id=1&size=5")
        btc_data = r.json()
        btc_prices = btc_data.get("items", [])
        if btc_prices:
            btc_close = btc_prices[0]["close"]
            record("BTC price exists", btc_close > 0, f"BTC=${btc_close:,.2f}")
        else:
            record("BTC price exists", False, "No records")

        # filter by asset_id=5 (MSFT)
        r = await c.get("/api/v1/prices?asset_id=5&size=5")
        msft_data = r.json()
        msft_prices = msft_data.get("items", [])
        if msft_prices:
            msft_close = msft_prices[0]["close"]
            record("MSFT price exists", msft_close > 0, f"MSFT=${msft_close:,.2f}")
        else:
            record("MSFT price exists", False, "No records (demo key limit)")

        # filter by asset_id=8 (USD/CNY)
        r = await c.get("/api/v1/prices?asset_id=8&size=5")
        fx_data = r.json()
        fx_prices = fx_data.get("items", [])
        if fx_prices:
            fx_close = fx_prices[0]["close"]
            record("USD/CNY rate exists", fx_close > 0, f"USD/CNY={fx_close}")
        else:
            record("USD/CNY rate exists", False, "No records")

        # ── 5. Trigger fetch ──────────────────────────────
        print("\n[5] Trigger live fetch")
        r = await c.post("/api/v1/prices/fetch/1")
        record("Fetch crypto", r.status_code == 200, f"fetched={r.json().get('fetched')}")

        r = await c.post("/api/v1/prices/fetch/3")
        record("Fetch FX", r.status_code == 200, f"fetched={r.json().get('fetched')}")

        # ── 6. Provider registry ──────────────────────────
        print("\n[6] Provider registry")
        r = await c.get("/api/v1/sources/registry/providers")
        providers = r.json().get("providers", [])
        record("Registry has crypto", "crypto_coingecko" in providers)
        record("Registry has stock", "stock_alpha_vantage" in providers)
        record("Registry has fx", "fx_exchange_rate" in providers)

        # ── 7. TradingView page ───────────────────────────
        print("\n[7] TradingView integration")
        r = await c.get("/tradingview")
        record("TradingView page", r.status_code == 200 and "lightweight-charts" in r.text)

        # ── 8. Swagger docs ───────────────────────────────
        print("\n[8] API docs")
        r = await c.get("/docs")
        record("Swagger UI", r.status_code == 200)
        r = await c.get("/openapi.json")
        record("OpenAPI schema", r.status_code == 200 and "paths" in r.json())

    # ── Summary ───────────────────────────────────
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"  Total: {len(results)}  |  {PASS}: {passed}  |  {FAIL}: {failed}")
    print("=" * 60)

    if failed:
        print("\n  Failed tests:")
        for name, ok, detail in results:
            if not ok:
                print(f"    - {name}  {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
