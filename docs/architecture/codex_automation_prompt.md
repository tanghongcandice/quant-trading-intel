# Codex 自动化：每日盘前采集

每天按计划运行美股盘前信息采集和入库。

## 任务

1. 运行本地后端采集入口。
2. 采集 X、Discord、Substack 高质量信息源。
3. 默认采集窗口为过去 24 小时；周一扩大到过去 72 小时。
4. 将数据归一化为 `information_item.v1`。
5. 写入本地 SQLite：`data/quant_intel.sqlite`。
6. 生成当天 `premarket_report.v1` 快照。
7. 输出采集摘要：每个来源数量、失败来源、最新发布时间、数据库路径、报告路径。

## 约束

- 单个来源失败不应中断其他来源。
- 不要打印 cookies、tokens 或任何敏感凭据。
- Discord 如果走浏览器采集，需要标注 partial，不要假装完整。
- 采集时间筛选必须以 `created_at` / `published_at` 为准，而不是 `collected_at`。
- 入库必须去重。

## 期望输出

```text
采集完成：
- run_id:
- 数据库:
- 采集窗口:
- X:
- Discord:
- Substack:
- 入库新增:
- 去重跳过:
- 错误:
- 日报快照:
```
