# 插件说明与开发指南

## 1. 现有插件

### 1.1 Crypto 插件 (`app/plugins/crypto/`)

| 项目 | 值 |
|------|-----|
| Key | `crypto` |
| 名称 | Cryptocurrency |
| 数据源 | CoinGecko 免费 API |
| Provider Key | `crypto_coingecko` |
| 默认资产 | BTC, ETH, SOL |
| 默认间隔 | 60,000ms (1 分钟) |
| API Key | 不需要 |

**特点**：
- 支持 10+ 种加密货币（BTC, ETH, SOL, BNB, XRP, DOGE, ADA, AVAX, DOT, MATIC）
- Symbol → CoinGecko ID 映射通过 `_COIN_MAP` 字典维护
- 返回 USD 计价的价格、24h 成交量、24h 涨跌幅
- 免费 API 速率限制约 10-30 次/分钟

### 1.2 Stock 插件 (`app/plugins/stock/`)

| 项目 | 值 |
|------|-----|
| Key | `stock` |
| 名称 | US Stocks |
| 数据源 | Stooq (免费) |
| Provider Key | `stock_stooq` |
| 默认资产 | AAPL, MSFT, GOOGL, TSLA |
| 默认间隔 | 300,000ms (5 分钟) |
| API Key | 不需要 |

**特点**：
- 使用 Stooq 免费 JSON API，无需注册
- 支持完整 OHLCV 数据（Open, High, Low, Close, Volume）
- 批量查询：URL 中 symbol 用 `+` 连接（如 `aapl.us+msft.us`）
- 非交易时段返回上一交易日收盘价
- Symbol 自动添加 `.us` 后缀

### 1.3 FX 插件 (`app/plugins/fx/`)

| 项目 | 值 |
|------|-----|
| Key | `fx` |
| 名称 | Foreign Exchange |
| 数据源 | ExchangeRate-API (免费) |
| Provider Key | `fx_exchange_rate` |
| 默认资产 | USD/CNY, EUR/USD, GBP/USD, USD/JPY |
| 默认间隔 | 120,000ms (2 分钟) |
| API Key | 不需要 |

**特点**：
- ExchangeRate-API 免费版每日更新一次
- 自动解析 `BASE/QUOTE` 格式的货币对
- 计算交叉汇率（如 EUR/USD 通过 EUR→USD 和 USD→USD 推算）

---

## 2. 插件开发流程

本节将手把手指导如何开发一个新插件。以添加 **贵金属（Gold / Silver）** 插件为例。

### 2.1 目录结构

在 `app/plugins/` 下创建新子包：

```
app/plugins/metal/
├── __init__.py       # ViewModel — 插件入口
├── config.yaml       # 配置文件
├── model.py          # Model — 数据源定义
├── provider.py       # Provider — API 调用实现
└── view.py           # View — Grafana 面板定义
```

### 2.2 Step 1: 实现 Provider

Provider 是与外部 API 交互的核心组件，需继承 `BaseDataProvider`。

```python
# app/plugins/metal/provider.py
"""贵金属数据 Provider — 调用 MetalPrice API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger

from app.providers import BaseDataProvider, PricePoint


class MetalProvider(BaseDataProvider):
    """从 MetalPrice API 获取贵金属价格."""

    # ❶ 必须定义唯一的 PROVIDER_KEY
    PROVIDER_KEY = "metal_price"

    def __init__(self, base_url: str = "", api_key: str = "", **kw: Any) -> None:
        super().__init__(base_url or "https://api.metalprice.example.com", api_key, **kw)
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30)

    # ❷ 必须实现 fetch_latest
    async def fetch_latest(self, symbols: list[str]) -> list[PricePoint]:
        """获取最新价格."""
        resp = await self._client.get(
            "/v1/latest",
            params={"symbols": ",".join(symbols), "key": self.api_key},
        )
        resp.raise_for_status()
        data = resp.json()

        points: list[PricePoint] = []
        for sym in symbols:
            price = data.get("rates", {}).get(sym)
            if price is None:
                logger.warning("No data for {}", sym)
                continue
            points.append(
                PricePoint(
                    symbol=sym,
                    timestamp=datetime.now(timezone.utc),
                    close=float(price),
                )
            )
        return points

    # ❸ 必须实现 fetch_history
    async def fetch_history(
        self, symbol: str, start: datetime, end: datetime,
    ) -> list[PricePoint]:
        """获取历史价格（按需实现，可返回空列表）."""
        return []

    # ❹ 建议：实现 close() 释放资源
    async def close(self) -> None:
        await self._client.aclose()
```

**要点**：
- `PROVIDER_KEY` 必须全局唯一，命名建议：`{类型}_{数据源}`
- `fetch_latest(symbols)` 返回 `list[PricePoint]`
- `fetch_history()` 可返回空列表（如不支持历史查询）
- 建议在 `close()` 中释放 HTTP 客户端

### 2.3 Step 2: 实现 Model

Model 定义数据源的默认配置和资产列表。

```python
# app/plugins/metal/model.py
"""贵金属插件 — Model 层."""

from __future__ import annotations

from typing import Any

from app.plugins import BasePluginModel, PluginConfig
from app.plugins.metal.provider import MetalProvider
from app.providers import BaseDataProvider


class MetalModel(BasePluginModel):
    """数据层：MetalPrice Provider + 默认贵金属资产."""

    def __init__(self, config: PluginConfig | None = None) -> None:
        super().__init__(config)

    def provider_class(self) -> type[BaseDataProvider]:
        # ❶ 返回 Provider 类（不是实例）
        return MetalProvider

    def default_source(self) -> dict[str, Any]:
        # ❷ 优先从 config.yaml 读取，否则使用硬编码默认值
        if self._config and self._config.source:
            return dict(self._config.source)
        return {
            "name": "Metal Prices",
            "provider": MetalProvider.PROVIDER_KEY,
            "base_url": "https://api.metalprice.example.com",
            "description": "Precious metal prices (Gold, Silver)",
        }

    def default_assets(self) -> list[dict[str, str]]:
        # ❸ 优先从 config.yaml 读取
        if self._config and self._config.assets:
            return self._config.assets
        return [
            {"symbol": "XAU", "display_name": "Gold (Troy Oz)"},
            {"symbol": "XAG", "display_name": "Silver (Troy Oz)"},
        ]
```

### 2.4 Step 3: 实现 View

View 定义 Grafana 面板。

```python
# app/plugins/metal/view.py
"""贵金属插件 — View 层 (Grafana 面板)."""

from __future__ import annotations

from app.plugins import BasePluginView, GrafanaPanelDef


class MetalView(BasePluginView):
    """展示层：为每种贵金属生成时序图面板."""

    def grafana_panels(
        self, source_id: int, asset_map: dict[str, int],
    ) -> list[GrafanaPanelDef]:
        panels: list[GrafanaPanelDef] = []
        for symbol, asset_id in asset_map.items():
            panels.append(
                GrafanaPanelDef(
                    panel_type="timeseries",
                    title=f"Metal — {symbol}",
                    width=12,
                    height=8,
                    url_path=f"/api/v1/prices?asset_id={asset_id}&size=500",
                    root_selector="items",
                    columns=[
                        {"selector": "timestamp", "text": "Time", "type": "timestamp"},
                        {"selector": "close", "text": "Price (USD)", "type": "number"},
                    ],
                    field_config={
                        "defaults": {
                            "color": {"mode": "palette-classic"},
                            "custom": {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 10},
                        }
                    },
                )
            )
        return panels
```

### 2.5 Step 4: 创建配置文件

```yaml
# app/plugins/metal/config.yaml
# ─────────────────────────────────────────────────────────────
# Precious Metal Plugin Configuration
# ─────────────────────────────────────────────────────────────

# Fetch interval in milliseconds (minimum: 1ms)
fetch_interval_ms: 300000

# Data source settings
source:
  name: "Metal Prices"
  provider: "metal_price"
  base_url: "https://api.metalprice.example.com"
  description: "Precious metal prices (Gold, Silver)"

# Path to API key file (empty = no key needed)
api_key_file: ""

# Tracked assets
assets:
  - symbol: "XAU"
    display_name: "Gold (Troy Oz)"
  - symbol: "XAG"
    display_name: "Silver (Troy Oz)"
```

### 2.6 Step 5: 实现 ViewModel（插件入口）

这是插件的 **入口文件**，PluginManager 通过模块级 `plugin` 变量自动发现它。

```python
# app/plugins/metal/__init__.py
"""贵金属插件 — ViewModel (MVVM 入口)."""

from __future__ import annotations

from pathlib import Path

from app.models import SourceCategory
from app.plugins import BasePlugin, IntervalConfig, PluginConfig
from app.plugins.metal.model import MetalModel
from app.plugins.metal.view import MetalView

_CONFIG_PATH = Path(__file__).parent / "config.yaml"


class MetalPlugin(BasePlugin):
    """ViewModel：贵金属价格追踪."""

    def __init__(self) -> None:
        cfg = PluginConfig(_CONFIG_PATH)
        super().__init__(
            model=MetalModel(config=cfg),
            view=MetalView(),
            interval=IntervalConfig(fetch_interval_ms=300_000),
            config=cfg,
        )

    @property
    def key(self) -> str:
        return "metal"          # ❶ 唯一标识符

    @property
    def name(self) -> str:
        return "Precious Metals" # ❷ 显示名称

    @property
    def description(self) -> str:
        return "Precious metal prices — Gold, Silver"

    @property
    def category(self) -> SourceCategory:
        return SourceCategory.CUSTOM  # ❸ 分类（CRYPTO/STOCK/FX/CUSTOM）


# ❹ 必须暴露 module-level `plugin` 变量
plugin = MetalPlugin()
```

### 2.7 Step 6: 验证

```bash
# 重新构建并启动
docker compose up -d --build api

# 检查插件是否被发现
curl http://localhost:8000/api/v1/plugins | python3 -m json.tool

# 检查配置
curl http://localhost:8000/api/v1/plugins/metal/config | python3 -m json.tool

# 查看日志
docker logs asset_api --tail 20
```

日志中应出现：
```
Loaded plugin config from /app/app/plugins/metal/config.yaml
Discovered plugin: Precious Metals (metal)
Registered provider: metal_price
```

---

## 3. 开发规范

### 3.1 命名约定

| 项目 | 格式 | 示例 |
|------|------|------|
| 插件目录 | 小写单词 | `crypto`, `stock`, `fx`, `metal` |
| Plugin Key | 与目录名一致 | `"crypto"`, `"metal"` |
| Provider Key | `{类型}_{数据源}` | `"crypto_coingecko"`, `"metal_price"` |
| Category | SourceCategory 枚举 | `CRYPTO`, `STOCK`, `FX`, `CUSTOM` |

### 3.2 必须实现的接口

#### Provider (`BaseDataProvider`)
```python
PROVIDER_KEY: ClassVar[str]                              # 全局唯一 Key
async def fetch_latest(symbols: list[str]) -> list[PricePoint]  # 最新价格
async def fetch_history(symbol, start, end) -> list[PricePoint] # 历史价格
async def close() -> None                                # 资源释放（建议）
```

#### Model (`BasePluginModel`)
```python
def provider_class() -> type[BaseDataProvider]    # Provider 类
def default_source() -> dict[str, Any]            # 数据源默认配置
def default_assets() -> list[dict[str, str]]      # 默认资产列表
```

#### View (`BasePluginView`)
```python
def grafana_panels(source_id, asset_map) -> list[GrafanaPanelDef]  # Grafana 面板
```

#### ViewModel (`BasePlugin`)
```python
key: str                    # 唯一标识（属性）
name: str                   # 显示名称（属性）
category: SourceCategory    # 分类（属性）
```

### 3.3 config.yaml 规范

必须包含以下顶级字段：

```yaml
fetch_interval_ms: 60000     # 必填，采集间隔（ms）
source:                       # 必填，数据源信息
  name: "..."
  provider: "..."
  base_url: "..."
  description: "..."
api_key_file: ""              # 必填（空字符串 = 无 Key）
assets:                       # 可选，资产列表
  - symbol: "..."
    display_name: "..."
```

可自由添加额外字段（如 `timeout`, `max_retries` 等），通过 `config.get("my_key")` 访问。

### 3.4 自动发现机制

PluginManager 的 `discover()` 方法会：

1. 扫描 `app/plugins/` 下的所有**子包**（含 `__init__.py` 的目录）
2. 导入子包模块
3. 查找模块级 `plugin` 变量
4. 检查 `plugin` 是否是 `BasePlugin` 的实例
5. 以 `plugin.key` 为键注册到插件管理器

> **因此，要让新插件生效，只需：**
> 1. 在 `app/plugins/` 下创建子包
> 2. 在 `__init__.py` 中定义 `plugin = YourPlugin()`
> 3. 重启服务

### 3.5 API Key 管理

如果插件需要 API Key：

1. 将 Key 写入文件（如 `app/plugins/metal/api.key`）
2. 在 `.gitignore` 中排除 `*.key` 文件
3. 在 `config.yaml` 中设置 `api_key_file: "api.key"`（相对路径基于 config.yaml 所在目录）
4. Provider 可通过 `self.api_key` 获取到 Key（由框架自动读取并注入）

### 3.6 调试技巧

```bash
# 查看所有已注册的 Provider
curl http://localhost:8000/api/v1/sources | python3 -m json.tool

# 查看插件详细信息（含 MVVM 各层数据）
curl http://localhost:8000/api/v1/plugins/metal | python3 -m json.tool

# 临时调高采集频率进行测试
curl -X PATCH http://localhost:8000/api/v1/plugins/metal/config \
  -H "Content-Type: application/json" \
  -d '{"fetch_interval_ms": 5000}'

# 查看实时日志
docker logs asset_api -f --tail 20

# 测试完记得恢复间隔
curl -X PATCH http://localhost:8000/api/v1/plugins/metal/config \
  -H "Content-Type: application/json" \
  -d '{"fetch_interval_ms": 300000}'
```

---

## 4. 扩展 SourceCategory

如果 `CRYPTO / STOCK / FX / CUSTOM` 不能满足需要，可在 `app/models.py` 的 `SourceCategory` 枚举中添加：

```python
class SourceCategory(str, enum.Enum):
    CRYPTO = "crypto"
    STOCK = "stock"
    FX = "fx"
    COMMODITY = "commodity"   # ← 新增
    CUSTOM = "custom"
```

添加后需要重建数据库（`docker compose down -v && docker compose up -d`），或使用 Alembic 迁移。

## 5. 核心类 API 速查

| 类 | 模块 | 说明 |
|----|------|------|
| `BaseDataProvider` | `app.providers` | 数据提供者抽象基类 |
| `PricePoint` | `app.providers` | 标准化价格数据点 |
| `ProviderRegistry` | `app.providers` | Provider 单例注册表 |
| `BasePlugin` | `app.plugins` | ViewModel 抽象基类 |
| `BasePluginModel` | `app.plugins` | Model 抽象基类 |
| `BasePluginView` | `app.plugins` | View 抽象基类 |
| `PluginConfig` | `app.plugins` | YAML 配置读写器 |
| `PluginManager` | `app.plugins` | 插件管理器（单例） |
| `IntervalConfig` | `app.plugins` | 采集间隔配置 |
| `GrafanaPanelDef` | `app.plugins` | Grafana 面板声明描述符 |
