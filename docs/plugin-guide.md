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

在 `app/plugins/` 下创建新子包（声明式插件只需 3 个文件）：

```
app/plugins/metal/
├── __init__.py       # 入口 — 3 行即可
├── config.yaml       # 元数据 + 数据源 + 面板 + 资产
└── provider.py       # Provider — API 调用实现
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

### 2.3 Step 2: 创建配置文件

声明式插件的所有配置（元数据 + 数据源 + 面板 + 资产）都在 `config.yaml` 中：

```yaml
# app/plugins/metal/config.yaml
# ─────────────────────────────────────────────────────────────
# Precious Metal Plugin Configuration
# ─────────────────────────────────────────────────────────────

# 插件元数据
key: "metal"
name: "Precious Metals"
category: "custom"
description: "Precious metal prices — Gold, Silver"
version: "1.0.0"

# Grafana 面板显示
panel_title_prefix: "Metal"
close_column_label: "Price (USD)"

# Fetch interval in milliseconds (minimum: 1ms)
fetch_interval_ms: 300000

# Data source settings
source:
  name: "Metal Prices"
  provider: "metal_price"
  base_url: "https://api.metalprice.example.com"
  description: "Precious metal prices (Gold, Silver)"

# API key file path (empty = no key needed)
api_key_file: ""

# Tracked assets
assets:
  - symbol: "XAU"
    display_name: "Gold (Troy Oz)"
  - symbol: "XAG"
    display_name: "Silver (Troy Oz)"
```

**config.yaml 标准字段说明**：

| 字段 | 说明 |
|------|------|
| `key` | 唯一标识符（与目录名一致） |
| `name` | 显示名称 |
| `category` | 分类（`crypto` / `stock` / `fx` / `custom`） |
| `description` | 描述文字 |
| `version` | 插件版本 |
| `panel_title_prefix` | Grafana 面板标题前缀（如 "Metal — XAU"） |
| `close_column_label` | 面板中价格列的标签（如 "Price (USD)"、"Close"、"Rate"） |
| `fetch_interval_ms` | 采集间隔（毫秒） |
| `source` | 数据源配置 |
| `api_key_file` | API Key 文件路径（空 = 不需要） |
| `assets` | 资产列表 |

### 2.4 Step 3: 创建入口文件

声明式插件的入口只需 **3 行代码**：

```python
# app/plugins/metal/__init__.py
"""贵金属插件 — 声明式配置."""

from app.plugins.defaults import create_plugin
from app.plugins.metal.provider import MetalProvider

plugin = create_plugin(__file__, MetalProvider)
```

`create_plugin()` 会自动：
1. 读取同目录下的 `config.yaml`
2. 生成 `DefaultPluginModel`（读取 source + assets）
3. 生成 `DefaultPluginView`（生成标准时序面板）
4. 生成 `DeclarativePlugin`（读取元数据）

### 2.5 Step 4: 验证

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

> **声明式插件**只需实现 Provider + 编写 config.yaml，Model / View / ViewModel 由框架自动生成。

#### 高级场景：自定义 Model / View

如果标准时序面板不能满足需求，可自定义 Model 或 View：

```python
# 自定义 View 示例
from app.plugins import BasePluginView, GrafanaPanelDef

class CustomView(BasePluginView):
    def grafana_panels(self, source_id, asset_map):
        # 返回自定义面板列表
        ...

# 在 __init__.py 中传入
plugin = create_plugin(__file__, MyProvider, view=CustomView())
```

### 3.3 config.yaml 规范

标准字段（声明式必填）：

```yaml
# 元数据
key: "metal"                  # 唯一标识
name: "Precious Metals"       # 显示名称
category: "custom"            # 分类 (crypto/stock/fx/custom)
description: "..."            # 描述
version: "1.0.0"              # 版本

# 面板显示
panel_title_prefix: "Metal"   # Grafana 面板标题前缀
close_column_label: "Close"   # 价格列标签（Close / Rate / Price …）

# 采集
fetch_interval_ms: 60000     # 采集间隔（ms）

# 数据源
source:
  name: "..."
  provider: "..."
  base_url: "..."
  description: "..."

api_key_file: ""              # API Key 文件路径

# 资产
assets:
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
> 2. 编写 `config.yaml` + `provider.py`
> 3. 在 `__init__.py` 中调用 `plugin = create_plugin(__file__, MyProvider)`
> 4. 重启服务

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
| `BasePlugin` | `app.plugins.base` | ViewModel 抽象基类 |
| `BasePluginModel` | `app.plugins.base` | Model 抽象基类 |
| `BasePluginView` | `app.plugins.base` | View 抽象基类 |
| `DeclarativePlugin` | `app.plugins.defaults` | 配置驱动的 ViewModel（推荐） |
| `DefaultPluginModel` | `app.plugins.defaults` | 配置驱动的 Model |
| `DefaultPluginView` | `app.plugins.defaults` | 配置驱动的 View |
| `create_plugin()` | `app.plugins.defaults` | 声明式插件工厂函数 |
| `PluginConfig` | `app.plugins.config` | YAML 配置读写器 |
| `PluginManager` | `app.plugins.manager` | 插件管理器（单例） |
| `IntervalConfig` | `app.plugins.base` | 采集间隔配置 |
| `GrafanaPanelDef` | `app.plugins.base` | Grafana 面板声明描述符 |

> 所有类均可从 `app.plugins` 直接导入（向后兼容）。
