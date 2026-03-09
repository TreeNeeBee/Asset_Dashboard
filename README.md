# Asset Dashboard

> **Python + TradingView + Grafana + Database** — 统一资产看板系统

## 系统架构

```
┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│  TradingView │◄────│  FastAPI REST  │────►│  PostgreSQL  │
│  (Browser)   │     │   API Server   │     │  / SQLite    │
└──────────────┘     └───────┬───────┘     └──────────────┘
                             │
                     ┌───────▼───────┐
                     │    Grafana    │
                     │   Dashboard   │
                     └───────────────┘
                             ▲
         ┌───────────────────┼───────────────────┐
         │                   │                   │
  ┌──────▼──────┐    ┌──────▼──────┐    ┌──────▼──────┐
  │  CoinGecko  │    │Alpha Vantage│    │ExchangeRate │
  │  (Crypto)   │    │  (US Stock) │    │    (FX)     │
  └─────────────┘    └─────────────┘    └─────────────┘
```

## 核心特性

| 功能 | 说明 |
|------|------|
| **标准数据接口** | `BaseDataProvider` 抽象基类，统一 `fetch_latest` / `fetch_history` 接口 |
| **提供者注册表** | `ProviderRegistry` 单例，支持运行时动态注册 / 注销数据源 |
| **动态增删** | REST API 提供 DataSource、Asset 的完整 CRUD，无需重启即可增删 |
| **BTC / 加密货币** | CoinGecko 免费 API，支持 BTC、ETH、SOL 等 |
| **美股** | Alpha Vantage API（`demo` key 或付费 key） |
| **汇率** | ExchangeRate-API 免费接口，支持 USD/CNY、EUR/USD 等 |
| **TradingView 图表** | 内嵌 Lightweight Charts™ K线 + 成交量图 |
| **Grafana 看板** | 预配置 Dashboard JSON + Infinity 数据源插件 |
| **定时采集** | APScheduler 后台定时拉取所有活跃资产的最新价格 |

## 目录结构

```
asset_dashboard/
├── app/
│   ├── __init__.py
│   ├── config.py            # Pydantic Settings（环境变量）
│   ├── database.py          # SQLAlchemy async engine
│   ├── models.py            # ORM 模型（DataSource / Asset / PriceRecord）
│   ├── schemas.py           # Pydantic 请求 / 响应模型
│   ├── main.py              # FastAPI 入口
│   ├── scheduler.py         # APScheduler 定时任务
│   ├── grafana.py           # Grafana Dashboard JSON 构建器
│   ├── tradingview.py       # TradingView Lightweight Charts 页面
│   ├── seed.py              # 数据库种子脚本
│   ├── providers/
│   │   ├── __init__.py      # BaseDataProvider + ProviderRegistry
│   │   ├── crypto_provider.py   # CoinGecko（BTC / ETH …）
│   │   ├── stock_provider.py    # Alpha Vantage（AAPL / MSFT …）
│   │   └── fx_provider.py       # ExchangeRate-API（USD/CNY …）
│   └── routers/
│       ├── __init__.py
│       ├── sources.py       # /api/v1/sources  CRUD
│       ├── assets.py        # /api/v1/assets   CRUD
│       └── prices.py        # /api/v1/prices   查询 + 触发拉取
├── grafana/
│   ├── dashboards/          # 预配置 dashboard JSON
│   └── provisioning/        # Grafana 自动供给配置
├── docker-compose.yml       # 一键部署：API + PostgreSQL + Grafana
├── Dockerfile
├── requirements.txt
├── pyproject.toml
└── .env.example
```

## 快速启动

### 方式 1：Docker Compose（推荐）

```bash
cd asset_dashboard
cp .env.example .env           # 按需修改环境变量
docker compose up -d --build
```

服务启动后：

| 服务 | 地址 |
|------|------|
| **API (Swagger)** | http://localhost:8000/docs |
| **TradingView 图表** | http://localhost:8000/tradingview |
| **Grafana** | http://localhost:3000（admin / admin） |

### 方式 2：本地开发

```bash
cd asset_dashboard
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 初始化数据库并写入种子数据
python -m app.seed

# 启动开发服务器
python -m app.main
```

## REST API 接口一览

### DataSource 数据源管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/sources` | 分页列出数据源 |
| GET | `/api/v1/sources/{id}` | 获取单个数据源 |
| POST | `/api/v1/sources` | **新增**数据源 |
| PATCH | `/api/v1/sources/{id}` | **修改**数据源 |
| DELETE | `/api/v1/sources/{id}` | **删除**数据源（级联删除关联资产） |
| GET | `/api/v1/sources/registry/providers` | 查看已注册的 Provider |

### Asset 资产管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/assets` | 分页列出资产（支持 `source_id` / `active_only` 筛选） |
| GET | `/api/v1/assets/{id}` | 获取单个资产 |
| POST | `/api/v1/assets` | **新增**资产 |
| PATCH | `/api/v1/assets/{id}` | **修改**资产 |
| DELETE | `/api/v1/assets/{id}` | **删除**资产 |

### Price 价格数据

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/prices` | 分页查询价格记录（支持 `asset_id` / 时间区间） |
| POST | `/api/v1/prices` | 手动写入一条价格记录 |
| POST | `/api/v1/prices/fetch/{source_id}` | **立即触发**某数据源的价格拉取 |

## 数据接口标准（扩展指南）

所有数据源均继承 `BaseDataProvider`：

```python
class BaseDataProvider(abc.ABC):
    PROVIDER_KEY: ClassVar[str] = ""  # 唯一标识

    async def fetch_latest(self, symbols: list[str]) -> list[PricePoint]: ...
    async def fetch_history(self, symbol: str, start: datetime, end: datetime) -> list[PricePoint]: ...
    async def health_check(self) -> bool: ...
    async def close(self) -> None: ...
```

### 添加新的数据源

1. 在 `app/providers/` 下新建 `my_provider.py`
2. 继承 `BaseDataProvider`，设置 `PROVIDER_KEY`
3. 实现 `fetch_latest` 和 `fetch_history`
4. 文件末尾调用 `registry.register(MyProvider)`
5. 在 `app/main.py` 中 `import app.providers.my_provider`
6. 通过 REST API 创建对应的 DataSource 记录

```python
# app/providers/my_provider.py
from app.providers import BaseDataProvider, PricePoint, registry

class MyCustomProvider(BaseDataProvider):
    PROVIDER_KEY = "custom_my_source"

    async def fetch_latest(self, symbols):
        # 实现数据获取逻辑
        return [PricePoint(symbol=s, timestamp=..., close=...) for s in symbols]

    async def fetch_history(self, symbol, start, end):
        return []

registry.register(MyCustomProvider)
```

### 动态注册/注销（运行时）

```python
from app.providers import registry

# 注册
registry.register(MyProvider)

# 注销
registry.unregister("custom_my_source")

# 查看当前已注册的 provider
registry.list_keys()
```

## Grafana 配置说明

- 使用 **Infinity** 数据源插件从 REST API 拉取 JSON 数据
- Dashboard 通过 volume mount 自动加载到 Grafana
- 支持自定义面板：时序图、表格、统计卡片
- 可通过 `app/grafana.py` 的 `build_dashboard_model()` 程序化生成

## TradingView 集成

访问 `http://localhost:8000/tradingview` 查看内嵌的 K 线图：

- 基于 [Lightweight Charts™](https://github.com/nicholasgasior/lightweight-charts)（MIT）
- 支持切换不同 Asset ID
- 实时从 REST API 拉取数据
- 蜡烛图 + 成交量柱状图

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.0 (async) |
| 数据库 | PostgreSQL (生产) / SQLite (开发) |
| 定时任务 | APScheduler |
| 前端图表 | TradingView Lightweight Charts |
| 监控看板 | Grafana + Infinity Plugin |
| 容器化 | Docker + Docker Compose |
