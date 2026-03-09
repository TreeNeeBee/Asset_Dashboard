# 使用指南

## 1. 快速启动

### 前置要求

- Docker Desktop (macOS / Windows) 或 Docker Engine + Compose (Linux)
- Git

### 一键部署

```bash
# 1. 克隆仓库
git clone git@github.com:TreeNeeBee/Asset_Dashboard.git
cd Asset_Dashboard

# 2. 创建环境变量文件
cp .env.example .env
# 按需编辑 .env，填入 API Key（大部分数据源免费，无需 Key）

# 3. 启动全部服务
docker compose up -d

# 4. 查看服务状态
docker compose ps
```

启动后访问：
- **API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **Grafana**: http://localhost:3000 （用户名/密码: `admin` / `admin`）

### 本地开发

```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 使用 SQLite 本地开发（无需 PostgreSQL）
# 默认 DATABASE_URL 即可

# 启动开发服务器（热重载）
uvicorn app.main:app --reload --port 8000
```

## 2. 访问 Grafana 看板

1. 打开 http://localhost:3000
2. 首次登录：`admin` / `admin`（可跳过修改密码）
3. 左侧菜单 → **Dashboards** → 选择 **Asset Dashboard**
4. 看板会自动从 API 拉取数据并展示价格走势

> Grafana 使用 Infinity 插件以 JSON 格式从 API 读取数据，所有面板由插件 View 层自动生成。

## 3. API 使用

### 3.1 查看所有插件

```bash
curl http://localhost:8000/api/v1/plugins | python3 -m json.tool
```

返回示例：
```json
{
  "total": 3,
  "plugins": [
    {"key": "crypto", "name": "Cryptocurrency", "fetch_interval_ms": 60000, ...},
    {"key": "stock",  "name": "US Stocks",      "fetch_interval_ms": 300000, ...},
    {"key": "fx",     "name": "Foreign Exchange","fetch_interval_ms": 120000, ...}
  ]
}
```

### 3.2 查看插件配置

```bash
curl http://localhost:8000/api/v1/plugins/crypto/config | python3 -m json.tool
```

### 3.3 修改采集间隔

通过 API 热更新（无需重启），同时持久化到 YAML 和数据库：

```bash
# 将 crypto 的采集间隔改为 30 秒
curl -X PATCH http://localhost:8000/api/v1/plugins/crypto/config \
  -H "Content-Type: application/json" \
  -d '{"fetch_interval_ms": 30000}'
```

### 3.4 修改跟踪的资产

```bash
# 将 crypto 只跟踪 BTC 和 ETH
curl -X PATCH http://localhost:8000/api/v1/plugins/crypto/config \
  -H "Content-Type: application/json" \
  -d '{"assets": [
    {"symbol": "BTC", "display_name": "Bitcoin"},
    {"symbol": "ETH", "display_name": "Ethereum"}
  ]}'
```

> 注意：资产变更后需要重启以更新数据库种子数据。

### 3.5 查看价格数据

```bash
# 按资产 ID 查询最近 10 条价格
curl "http://localhost:8000/api/v1/prices?asset_id=1&size=10" | python3 -m json.tool

# 列出所有资产
curl http://localhost:8000/api/v1/assets | python3 -m json.tool
```

### 3.6 TradingView 图表

浏览器打开：
```
http://localhost:8000/tradingview/BTC
http://localhost:8000/tradingview/AAPL
```

## 4. 配置管理

### 4.1 环境变量 (.env)

`.env` 存放全局密钥和数据库连接信息：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | 数据库连接串 | `sqlite+aiosqlite:///./asset_dashboard.db` |
| `ALPHA_VANTAGE_API_KEY` | Alpha Vantage API Key | `demo` |
| `GRAFANA_API_KEY` | Grafana API Key（可选） | 空 |
| `FETCH_INTERVAL` | 全局默认采集间隔（秒） | `300` |

### 4.2 插件配置 (config.yaml)

每个插件有独立的 `config.yaml`，位于插件目录下：

```
app/plugins/crypto/config.yaml
app/plugins/stock/config.yaml
app/plugins/fx/config.yaml
```

配置字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `fetch_interval_ms` | int | 采集间隔（毫秒），最小 1ms |
| `source.name` | string | 数据源显示名称 |
| `source.provider` | string | Provider 注册 Key |
| `source.base_url` | string | API 基础 URL |
| `source.description` | string | 数据源描述 |
| `api_key_file` | string | API Key 文件路径（空 = 不需要） |
| `assets` | list | 跟踪的资产列表 |

### 4.3 配置修改方式

| 方式 | 操作 | 是否需要重启 |
|------|------|-------------|
| **PATCH API** | `curl -X PATCH /api/v1/plugins/{key}/config` | 否（热更新） |
| **编辑 YAML** | 直接修改 `config.yaml` 文件 | 是（`docker restart asset_api`） |

> Docker 已挂载 `./app/plugins` 到容器内，本地修改 YAML 文件后重启容器即可生效。

## 5. 常见操作

### 重启 API 服务

```bash
docker restart asset_api
```

### 查看 API 日志

```bash
docker logs asset_api --tail 50 -f
```

### 重新构建（修改了 Python 代码后）

```bash
docker compose up -d --build api
```

### 清理并重建数据库

```bash
docker compose down -v   # 删除所有 volume（包括数据库）
docker compose up -d     # 重新启动
```

### 查看 Swagger API 文档

浏览器打开 http://localhost:8000/docs，可以直接在界面上测试所有 API。

## 6. 数据源说明

### Cryptocurrency (CoinGecko)

- **免费 API**，无需 Key
- 速率限制：~10-30 请求/分钟
- 支持币种：BTC、ETH、SOL 等（可在 Provider 中扩展 `_COIN_MAP`）
- 默认间隔：60 秒

### US Stocks (Stooq)

- **免费 API**，无需 Key
- 返回上一交易日收盘数据（非实时）
- 非交易时段返回固定值
- 交易时间：美东 9:30-16:00（北京时间 22:30-次日5:00）
- 默认间隔：300 秒

### Foreign Exchange (ExchangeRate-API)

- **免费 API**，无需 Key
- 每日更新一次汇率
- 支持货币对：USD/CNY、EUR/USD、GBP/USD、USD/JPY
- 默认间隔：120 秒
