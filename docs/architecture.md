# 架构设计文档

## 1. 系统总览

Asset Dashboard 是一个 **统一资产看板系统**，采用 FastAPI + PostgreSQL + Grafana 技术栈，支持对加密货币、美股、外汇等多类资产进行实时价格采集与可视化展示。

系统采用 **MVVM 插件架构**，每种资产类型是一个独立插件，可自由扩展。

```
┌────────────────────────────────────────────────────────────────────┐
│                        Docker Compose                              │
│                                                                    │
│  ┌──────────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   FastAPI (API)  │  │  PostgreSQL  │  │      Grafana         │  │
│  │   :8000          │──│  :5432       │  │  :3000               │  │
│  │                  │  │              │  │  Infinity Plugin     │  │
│  │  ┌────────────┐  │  └──────────────┘  │  (JSON → Panel)     │  │
│  │  │PluginMgr   │  │                    │                      │  │
│  │  │ ┌────────┐ │  │                    │  ┌────────────────┐  │  │
│  │  │ │ crypto │ │  │◄───── HTTP ───────│  │  Dashboard     │  │  │
│  │  │ │ stock  │ │  │    /api/v1/...    │  │  (auto-gen)    │  │  │
│  │  │ │ fx     │ │  │                    │  └────────────────┘  │  │
│  │  │ └────────┘ │  │                    └──────────────────────┘  │
│  │  └────────────┘  │                                              │
│  │  ┌────────────┐  │                                              │
│  │  │APScheduler │  │   ← 定时采集各数据源                         │
│  │  └────────────┘  │                                              │
│  └──────────────────┘                                              │
└────────────────────────────────────────────────────────────────────┘
```

## 2. 技术栈

| 组件 | 技术 | 版本 | 用途 |
|------|------|------|------|
| Web 框架 | FastAPI | 0.109.0 | REST API 服务 |
| 异步运行时 | Uvicorn | 0.27.0 | ASGI 服务器 |
| ORM | SQLAlchemy | 2.0.25 | 数据库访问（async） |
| 数据库 | PostgreSQL | 16 | 持久化存储 |
| 调度器 | APScheduler | 3.10.4 | 定时价格采集 |
| 可视化 | Grafana OSS | 10.3.1 | 仪表板展示 |
| HTTP 客户端 | httpx | 0.26.0 | 调用外部数据源 API |
| 配置 | PyYAML | 6.0.1 | 插件配置文件 |
| 容器化 | Docker Compose | — | 一键部署 |

## 3. MVVM 插件架构

每个资产类型（crypto / stock / fx）是一个独立插件，遵循 **MVVM（Model-View-ViewModel）** 分层模式。

框架代码拆分为四个模块，保持关注点分离：

```
app/plugins/
├── __init__.py       # 公共 API 再导出 + plugin_manager 单例
├── base.py           # 抽象基类 + 数据类型（BasePlugin, IntervalConfig, GrafanaPanelDef …）
├── config.py         # PluginConfig — 读写 config.yaml（含元数据 + 面板配置）
├── defaults.py       # 配置驱动的默认实现（DefaultPluginModel, DefaultPluginView, DeclarativePlugin）
└── manager.py        # PluginManager — 自动发现 + Provider 注册
```

### 3.1 声明式插件（推荐）

标准插件只需 **2 个文件**：

```
app/plugins/<name>/
├── config.yaml       # 元数据 + 数据源 + 面板配置 + 资产列表
└── provider.py       # 具体 API 调用实现
```

再加上一个 **3 行入口**：

```python
# app/plugins/<name>/__init__.py
from app.plugins.defaults import create_plugin
from .<name>.provider import XProvider

plugin = create_plugin(__file__, XProvider)
```

`create_plugin()` 会自动读取 `config.yaml`，生成 DefaultPluginModel、DefaultPluginView 和 DeclarativePlugin。

### 3.2 config.yaml 完整格式

```yaml
# 插件元数据（声明式必填）
key: "crypto"
name: "Cryptocurrency"
category: "crypto"
description: "Cryptocurrency prices via CoinGecko free API"
version: "1.0.0"

# Grafana 面板显示（由 DefaultPluginView 使用）
panel_title_prefix: "Crypto"
close_column_label: "Close"

# 采集间隔
fetch_interval_ms: 60000

# 数据源
source:
  name: "CoinGecko Crypto"
  provider: "crypto_coingecko"
  base_url: "https://api.coingecko.com/api/v3"
  description: "..."

api_key_file: ""

# 资产列表
assets:
  - symbol: "BTC"
    display_name: "Bitcoin"
```

### 3.3 各层职责

#### Config (`PluginConfig` — `config.py`)
- 读写插件目录下的 `config.yaml`
- 提供全部标准字段的类型化访问器：`key`、`plugin_name`、`category`、`description`、`version`、`panel_title_prefix`、`close_column_label`、`fetch_interval_ms`、`source`、`assets`
- 支持 `read_api_key()` 从文件路径读取 API Key
- 额外自定义字段通过 `get()` / `set()` 访问

#### Model (`DefaultPluginModel` — `defaults.py`)
- 从 `config.yaml` 读取数据源配置和资产列表
- 仅需传入 Provider 类（不是实例）
- 如需自定义，继承 `BasePluginModel` 并传给 `create_plugin(model=...)`

#### View (`DefaultPluginView` — `defaults.py`)
- 从 `config.yaml` 读取 `panel_title_prefix` 和 `close_column_label`
- 自动生成标准时序面板（timeseries）
- 如需自定义面板样式，继承 `BasePluginView` 并传给 `create_plugin(view=...)`

#### ViewModel (`DeclarativePlugin` / `BasePlugin` — `base.py` + `defaults.py`)
- 核心协调者：绑定 Model ↔ View
- 从 `config.yaml` 读取元数据（key / name / category / version / description）
- `update_interval(ms)` 同步更新 IntervalConfig 和 PluginConfig（消除双重状态）
- 可选提供额外的 API Router

### 3.4 MVVM 数据流

```
                    ┌──────────────┐
                    │  config.yaml │
                    └──────┬───────┘
                           │ load
                    ┌──────▼───────┐
   ┌───────────┐   │  ViewModel   │   ┌───────────┐
   │   Model   │◄──│ (BasePlugin) │──►│   View    │
   │ seed data │   │  interval    │   │ panels    │
   │ provider  │   │  metadata    │   │           │
   └─────┬─────┘   └──────┬───────┘   └─────┬─────┘
         │                │                  │
         ▼                ▼                  ▼
    DataSource      APScheduler         Grafana
    + Assets        定时采集            Dashboard JSON
```

## 4. 数据流架构

### 4.1 启动流程

```
App Startup
    │
    ├── 1. validate_secrets()        — 校验 .env 中的密钥
    ├── 2. plugin_manager.discover() — 扫描 app/plugins/ 子包
    │       └── 每个插件: 加载 config.yaml → 实例化 Model/View/ViewModel
    ├── 3. register_providers()      — 注册所有 Provider 到全局 Registry
    ├── 4. init_db()                 — 创建表 + 插入种子数据
    ├── 5. start_scheduler()         — 启动 APScheduler
    └── 6. sync_scheduler_jobs()     — 为每个 DataSource 创建定时任务
```

### 4.2 数据采集流程

```
APScheduler Timer
    │
    ├── _fetch_single_source(source_id)
    │       │
    │       ├── 从 DB 读取 DataSource + Assets
    │       ├── 从 ProviderRegistry 创建 Provider 实例
    │       ├── 调用 provider.fetch_latest(symbols)
    │       │       └── HTTP 请求外部 API (CoinGecko / Stooq / ER-API)
    │       ├── 将 PricePoint → PriceRecord 写入 DB
    │       └── 关闭 Provider（释放 HTTP 连接）
    │
    └── 每个 DataSource 独立间隔执行
```

### 4.3 数据展示流程

```
Grafana Dashboard
    │
    ├── Infinity Plugin → GET /api/v1/prices?asset_id=X&size=500
    │                       └── FastAPI → SQLAlchemy → PostgreSQL
    │                           └── 返回 JSON: { items: [...] }
    │
    └── 面板渲染: 时序图 / 表格 / 统计卡片
```

## 5. 数据库模型

```
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│   data_sources   │       │     assets       │       │  price_records   │
├──────────────────┤       ├──────────────────┤       ├──────────────────┤
│ id (PK)          │───┐   │ id (PK)          │───┐   │ id (PK)          │
│ name (UNIQUE)    │   │   │ source_id (FK)   │   │   │ asset_id (FK)    │
│ category (ENUM)  │   └──►│ symbol           │   └──►│ timestamp        │
│ provider         │       │ display_name     │       │ open             │
│ base_url         │       │ metadata_json    │       │ high             │
│ api_key          │       │ is_active        │       │ low              │
│ description      │       │ created_at       │       │ close            │
│ fetch_interval_ms│       └──────────────────┘       │ volume           │
│ created_at       │                                   │ extra_json       │
└──────────────────┘                                   └──────────────────┘
```

- **DataSource**: 数据源注册（如 CoinGecko、Stooq），对应一个 Provider
- **Asset**: 资产（如 BTC、AAPL），隶属于某个 DataSource
- **PriceRecord**: 价格时序数据，OHLCV + 扩展 JSON

## 6. API 端点

### 核心 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/sources` | 列出所有数据源 |
| POST | `/api/v1/sources` | 创建数据源 |
| GET | `/api/v1/assets` | 列出所有资产 |
| POST | `/api/v1/assets` | 创建资产 |
| GET | `/api/v1/prices` | 查询价格（支持 `asset_id`、`size` 参数） |

### 插件管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/plugins` | 列出所有已加载插件 |
| GET | `/api/v1/plugins/{key}` | 插件详情（含 MVVM 层信息） |
| GET | `/api/v1/plugins/{key}/config` | 读取插件 YAML 配置 |
| PATCH | `/api/v1/plugins/{key}/config` | 更新插件配置（热更新） |
| PATCH | `/api/v1/plugins/{key}/interval` | 更新采集间隔 |

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/v1/dashboard/json` | 获取 Grafana Dashboard JSON |
| GET | `/tradingview/{symbol}` | TradingView 图表页面 |

## 7. 部署架构

Docker Compose 定义了三个服务：

| 服务 | 容器名 | 端口 | 说明 |
|------|--------|------|------|
| `api` | `asset_api` | 8000 | FastAPI 应用 |
| `postgres` | `asset_postgres` | 5432 | PostgreSQL 16 数据库 |
| `grafana` | `asset_grafana` | 3000 | Grafana 看板 |

Volume 挂载：
- `dashboard_json` — API 生成的 Dashboard JSON 共享给 Grafana
- `./app/plugins` → `/app/app/plugins` — 本地插件目录直通容器（支持热编辑 config.yaml）
- `pgdata` — PostgreSQL 持久化数据
- `grafana_data` — Grafana 持久化数据

## 8. 扩展性设计

| 维度 | 实现方式 |
|------|----------|
| **新资产类型** | 在 `app/plugins/` 下新建子包即可，PluginManager 自动发现 |
| **新数据源** | 实现 `BaseDataProvider`，在插件 Model 中引用 |
| **新面板类型** | 在插件 View 中定义 `GrafanaPanelDef` |
| **配置变更** | 编辑 `config.yaml` + 重启，或通过 PATCH API 热更新 |
| **自定义路由** | 在插件中重写 `api_router()` 方法返回 `APIRouter` |
