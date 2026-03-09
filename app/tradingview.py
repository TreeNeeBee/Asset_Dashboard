"""TradingView Lightweight Charts™ integration.

Serves a standalone HTML page that uses the TradingView lightweight-charts
library (open-source, MIT licence) to render candlestick + volume charts
with data pulled from our REST API.

The page is served by FastAPI at ``/tradingview``.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["TradingView"])

_TV_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Asset Dashboard — TradingView Chart</title>
<script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #131722; color: #d1d4dc; }
  #controls { display: flex; gap: 12px; padding: 16px; align-items: center; }
  #controls label { font-size: 14px; }
  #controls select, #controls button {
      background: #1e222d; border: 1px solid #363a45; color: #d1d4dc;
      padding: 6px 12px; border-radius: 4px; font-size: 14px; cursor: pointer;
  }
  #controls button:hover { background: #2a2e39; }
  #chart-container { width: 100%; height: calc(100vh - 60px); }
  .status { font-size: 12px; color: #787b86; padding: 0 16px; }
</style>
</head>
<body>

<div id="controls">
  <label for="asset-select">Asset ID:</label>
  <select id="asset-select">
    <option value="1">1 — BTC</option>
    <option value="2">2 — AAPL</option>
    <option value="3">3 — USD/CNY</option>
  </select>
  <label for="size-select">Records:</label>
  <select id="size-select">
    <option value="100">100</option>
    <option value="500" selected>500</option>
    <option value="1000">1000</option>
  </select>
  <button onclick="loadData()">&#x21bb; Refresh</button>
  <span class="status" id="status"></span>
</div>

<div id="chart-container"></div>

<script>
const API_BASE = window.location.origin;
const container = document.getElementById('chart-container');
const chart = LightweightCharts.createChart(container, {
    layout: { background: { color: '#131722' }, textColor: '#d1d4dc' },
    grid: { vertLines: { color: '#1e222d' }, horzLines: { color: '#1e222d' } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: '#363a45' },
    timeScale: { borderColor: '#363a45', timeVisible: true, secondsVisible: false },
});

const candleSeries = chart.addCandlestickSeries({
    upColor: '#26a69a', downColor: '#ef5350',
    borderUpColor: '#26a69a', borderDownColor: '#ef5350',
    wickUpColor: '#26a69a', wickDownColor: '#ef5350',
});

const volumeSeries = chart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: 'vol',
});
chart.priceScale('vol').applyOptions({
    scaleMargins: { top: 0.8, bottom: 0 },
});

async function loadData() {
    const assetId = document.getElementById('asset-select').value;
    const size = document.getElementById('size-select').value;
    const statusEl = document.getElementById('status');
    statusEl.textContent = 'Loading…';

    try {
        const resp = await fetch(`${API_BASE}/api/v1/prices?asset_id=${assetId}&size=${size}`);
        const json = await resp.json();
        const items = json.items || [];

        // Sort ascending by time
        items.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

        const candles = items.map(r => ({
            time: Math.floor(new Date(r.timestamp).getTime() / 1000),
            open:  r.open  ?? r.close,
            high:  r.high  ?? r.close,
            low:   r.low   ?? r.close,
            close: r.close,
        }));

        const volumes = items.map(r => ({
            time: Math.floor(new Date(r.timestamp).getTime() / 1000),
            value: r.volume ?? 0,
            color: (r.close >= (r.open ?? r.close)) ? 'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)',
        }));

        candleSeries.setData(candles);
        volumeSeries.setData(volumes);
        chart.timeScale().fitContent();
        statusEl.textContent = `Loaded ${items.length} records`;
    } catch (err) {
        statusEl.textContent = 'Error: ' + err.message;
    }
}

// Responsive resize
new ResizeObserver(() => {
    chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
}).observe(container);

// Initial load
loadData();
</script>
</body>
</html>
"""


@router.get("/tradingview", response_class=HTMLResponse)
async def tradingview_page():
    """Serve the TradingView lightweight-charts page."""
    return _TV_HTML


@router.get("/tradingview/assets", tags=["TradingView"])
async def tradingview_asset_list():
    """Return a simple asset list for the chart selector (consumed by JS)."""
    # In production, query the DB. For now a static hint:
    return {
        "hint": "Use the /api/v1/assets endpoint to list available assets "
                "and update the <select> dropdown dynamically."
    }
