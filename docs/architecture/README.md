# Quant Trading Intel 架构文档

这个目录是把当前信息采集/盘前日报系统升级成前后端分离项目的第一版设计。

## 文件

- `frontend_backend_architecture.md`：完整架构说明，包含前端、后端、数据库、自动化、进阶分析上下文。
- `api_contract.md`：前后端 API 契约。
- `database_schema.sql`：SQLite 第一版建表 SQL。
- `codex_automation_prompt.md`：Codex 每日自动化采集任务 prompt 草案。

## 第一阶段建议

1. 用 `database_schema.sql` 建本地 SQLite。
2. 把当前 `high_quality_items.jsonl` 导入 `information_items`、`item_entities`。
3. 做 FastAPI 查询接口：`/api/items`、`/api/context/item/{item_id}`。
4. 做前端信息库页面，先完成时间窗口筛选。
5. 做单条信息侧边栏，实现“复制给 Codex”。
6. 最后接 Codex 自动化，每天定时采集入库。
