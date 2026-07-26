# Quant Trading Intel

本项目是本地量化交易信息系统的主项目，已经把三个模块收束到同一个目录：

- 前端工作台：`apps/web`
- 数据库/FastAPI 后端：`apps/api`
- 自动化采集调度组件：`packages/ingestion_scheduler`
- 统一数据库：运行时生成的 `data/quant_intel.sqlite`

当前能力：

- SQLite schema、去重、ticker entity、FTS5 全文搜索。
- `information_item.v1` JSONL 入库。
- 时间窗口、来源、作者、标的、全文查询。
- 单条数据 Codex 进阶分析上下文组装。
- FastAPI 接口：`/health`、`/api/items`、`/api/items/{item_id}`、`/api/context/item/{item_id}`、`/api/runs`。
- 前端优先读取 FastAPI；后端不可用时自动 fallback 到不含真实采集内容的静态示例数据。
- 盘前采集入口支持 dry-run，不会触发真实外网采集。

## 公开仓库的数据边界

仓库只包含前后端代码、采集适配器、调度逻辑、数据结构和脱敏示例。以下内容只保留在本地，不会提交：

- SQLite 数据库和 X crawler 账户库。
- X、Substack、Discord 的真实采集结果与运行日志。
- Discord 私有频道消息、Cookie、Token、`.env` 和浏览器会话。
- Python 虚拟环境、缓存和构建产物。

克隆仓库后可先使用 `apps/web/data/sample_items.js` 查看完整前端结构，再按自己的授权信息源初始化本地数据库。

## 安装 API 依赖

FastAPI 和 uvicorn 是服务依赖。如果本机还没安装，在项目内执行：

```bash
cd quant-trading-intel/apps/api
python3 -m pip install -e .
```

## 初始化数据库

```bash
cd quant-trading-intel/apps/api
PYTHONPATH=. python3 -m app.jobs.init_db
```

## 导入现有 JSONL

```bash
cd quant-trading-intel/apps/api
PYTHONPATH=. python3 -m app.jobs.import_jsonl \
  --jsonl ../../../outputs/high_quality_sources_20260619/high_quality_items.jsonl \
  --mode historical_seed
```

## 查询样例

```bash
cd quant-trading-intel/apps/api
PYTHONPATH=. python3 -m app.jobs.query_items --ticker MU --limit 5
PYTHONPATH=. python3 -m app.jobs.query_items --start-at 2026-06-18T00:00:00Z --limit 5
```

## 构建 Codex 上下文

```bash
cd quant-trading-intel/apps/api
PYTHONPATH=. python3 -m app.jobs.build_context itm_xxx
```

## 自动化采集 dry-run

这个命令只验证本地 scheduler、配置和计划命令，不访问 X/Substack/Discord，也不会写入真实信息库：

```bash
cd quant-trading-intel/apps/api
PYTHONPATH=. python3 -m app.jobs.collect_premarket --dry-run
```

真实采集需要网络权限和对应采集 skill 的登录状态，确认后再去掉 `--dry-run`。

## 启动 API

安装依赖后：

```bash
cd quant-trading-intel/apps/api
uvicorn app.main:app --reload
```

默认地址：

```text
http://127.0.0.1:8000
```

## 打开前端

前端是静态页面，可以直接打开：

```text
quant-trading-intel/apps/web/index.html
```

也可以用本地静态服务：

```bash
cd quant-trading-intel/apps/web
python3 -m http.server 8001 --bind 127.0.0.1
```

前端默认请求：

```text
http://127.0.0.1:8000/api
```

如需改 API 地址，可在页面加载前设置：

```html
<script>
  window.__QUANT_INTEL_API_BASE__ = "http://127.0.0.1:8000/api";
</script>
```

## 一键本地验收

```bash
cd quant-trading-intel
./scripts/verify_local_system.sh
```

验收内容：

- SQLite `integrity_check=ok`
- `information_items=122`
- `item_entities=282`
- `information_items_fts=122`
- 后端 CLI 查询和 context 生成
- 采集 scheduler dry-run
- 前端迁入和脚本语法
- FastAPI 依赖、临时服务启动和核心接口返回
