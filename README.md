# Quant Trading Intel

当前版本：**v1.2**。版本变更与迁移说明见 [CHANGELOG.md](CHANGELOG.md)。

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
- 前端读取 FastAPI；后端不可用时明确显示“API 离线”，不会静默切换到旧数据。
- 盘前采集入口支持 dry-run，不会触发真实外网采集。

## 公开仓库的数据边界

仓库只包含前后端代码、采集适配器、调度逻辑、数据结构和脱敏示例。以下内容只保留在本地，不会提交：

- SQLite 数据库和 X crawler 账户库。
- X、Substack、Discord 的真实采集结果与运行日志。
- Discord 私有频道消息、Cookie、Token、`.env` 和浏览器会话。
- Python 虚拟环境、缓存和构建产物。

克隆仓库后可先使用 `apps/web/data/sample_items.js` 查看完整前端结构，再按自己的授权信息源初始化本地数据库。

## 设计文档

- 前后端总体架构：`docs/architecture/frontend_backend_architecture.md`
- API 契约：`docs/architecture/api_contract.md`
- Codex 自动化任务：`automations/premarket_collection_prompt.md`
- 每日盘前日报规范：`docs/report-design/premarket_report_design.md`
- 日报数据契约：`docs/report-design/report_contract.v1.json`

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
  --jsonl /path/to/information_items.jsonl \
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

真实采集需要网络权限和已授权的登录状态，确认后再去掉 `--dry-run`。三个 X 来源使用上一版 `x-crawler` helper，通过包装器输出 JSONL；helper 默认入口为：

```text
vendor/x-crawler/scripts/xcrawl.py
```

入口不在默认位置时，只需为采集服务设置路径，不要复制 Cookie、Token 或密码：

```bash
export X_CRAWLER_SKILL_SCRIPT=/实际路径/x-crawler/scripts/xcrawl.py
```

新机器第一次使用时，以项目虚拟环境打开独立的登录 profile：

```bash
.venv/bin/python scripts/xcrawl_project.py login
```

登录由用户在可视化 X 页面完成。`data/x_crawler/accounts.db` 只记录 profile 路径、账号名和验证时间，不保存密码、Cookie 或 Token。

Discord 与 Substack 也恢复为上一版的命令行采集链路，而不是读取预先生成的浏览器快照：

- Discord 使用 `scripts/discord_exporter_project.py export`，连接 `data/browser_profiles/discord` 中已登录的独立 profile；每个频道按成功游标向前重叠 2 小时滚动，原始 JSON 保留回复引用和附件，再由 Discord adapter 做作者过滤、父消息上下文、静态图片下载与标准化。
- Substack 使用 `scripts/substack_project.py download`，连接 `data/browser_profiles/substack`，从归档接口按游标发现文章并逐篇读取正文，原始 Markdown 保存在本次运行目录后再标准化。
- Club 500 两个频道在标准化后会与天益宗来源按规范化正文做跨来源精确去重，审计写入本次运行目录的 `cross_source_dedupe_audit.jsonl`。

这些 helper 只使用各自的项目 profile，不读取或输出 Chrome 密码、Cookie、Token。登录态失效时，可用可视化模式执行相同 helper 完成重新登录；自动任务不会静默回退到旧 JSON 快照。

Discord 完整性修复：消息列表加载失败或空提取均报错；聊天区域分段回滚，每 10 轮保存 `data/discord_checkpoints/<channel>.json`。未覆盖截止点时保留断点并拒绝成功，后续从已保存位置续采。`--ignore-cursor --after <ISO时间>` 可显式回补已推进游标之前的缺口。回复区头像不用于判断发言者，非目标作者仅作为回复上下文保存。

每日入口通过操作系统文件锁拒绝重叠启动，Discord profile 另有串行锁。Discord 的增量起点取主数据库成功导入游标；调度状态中出现过但尚未导入主库的记录仍会再次输出。未翻译的英文 Discord 记录保存在本轮 `pending_codex_review.jsonl`，状态为 `awaiting_codex_review`；Codex 复核并补齐翻译后再导入，不能把待复核视为已入库。

统一入口为：

```bash
./scripts/run_daily_collection.sh
```

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
