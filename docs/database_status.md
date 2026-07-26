# 后端数据库状态

生成日期：2026-06-20

## 数据库路径

```text
quant-trading-intel/data/quant_intel.sqlite
```

## 当前已完成

- 按项目目录创建后端数据库工程。
- 创建 SQLite schema。
- 创建 FTS5 全文搜索表。
- 导入现有 `information_item.v1` JSONL。
- 导入当前盘前日报 HTML 快照。
- 验证时间窗口、作者、标的、全文搜索、上下文复制包。
- 验证重复导入会跳过，不会重复写入。

## 数据量

| 表 | 数量 |
|---|---:|
| information_items | 122 |
| item_entities | 282 |
| information_items_fts | 122 |
| ingestion_runs | 2 |
| report_snapshots | 1 |

## 来源分布

| source_id | 数量 |
|---|---:|
| x_aleabitoreddit | 71 |
| x_haochihaochiaaa | 27 |
| discord_haochi_daqu | 8 |
| x_edgerunner17888 | 8 |
| discord_tianyi_edgerunner_trades | 7 |
| substack_edgerunner17888 | 1 |

## 常用命令

初始化数据库：

```bash
cd quant-trading-intel/apps/api
PYTHONPATH=. python3 -m app.jobs.init_db
```

导入当前历史数据：

```bash
cd quant-trading-intel/apps/api
PYTHONPATH=. python3 -m app.jobs.import_jsonl \
  --jsonl ../../../outputs/high_quality_sources_20260619/high_quality_items.jsonl \
  --mode historical_seed
```

查询 MU：

```bash
cd quant-trading-intel/apps/api
PYTHONPATH=. python3 -m app.jobs.query_items --ticker MU --limit 5
```

按发布时间窗口查询：

```bash
cd quant-trading-intel/apps/api
PYTHONPATH=. python3 -m app.jobs.query_items \
  --start-at 2026-06-18T00:00:00Z \
  --end-at 2026-06-19T23:59:59Z \
  --limit 5
```

生成 Codex 进阶分析上下文：

```bash
cd quant-trading-intel/apps/api
PYTHONPATH=. python3 -m app.jobs.build_context itm_4ebda57a16be455a5f9d6baa
```

## 后续

1. 安装 FastAPI/uvicorn 后启动 API。
2. 实现前端信息库页面。
3. 用 Codex automation 调用每日采集入口。
4. 增加 Discord 完整 adapter。
5. 增加行情模块，修正“已涨/未涨”的判定。
