# Codex 自动化：每日五次增量采集

每天在本地时间 00:00、08:00、11:00、16:00、20:00 运行增量采集。实际任务入口为：

```bash
./scripts/run_daily_collection.sh
```

1. 运行本地后端采集入口。
2. 采集 X、Discord、Substack，以及已配置的抖音和微信公众号文章。
3. 以上次成功时间为游标，并向前重叠 2 小时补漏。
4. 将数据归一化为 `information_item.v1`。
5. 写入本地 SQLite：`quant-trading-intel/data/quant_intel.sqlite`。
6. 生成当天 `premarket_report.v1` 快照。
7. 输出采集摘要：每个来源数量、失败来源、最新发布时间、数据库路径、报告路径。

约束：

- 单个来源失败不应中断其他来源。
- 不要打印 cookies、tokens 或任何敏感凭据。
- X、Discord、Substack 和抖音优先使用已授权的浏览器会话；不得读取或导出浏览器凭据。
- Discord 回复需要保留被回复消息上下文；静态图片可下载，跳过动图和视频。
- 抖音只采标题与口播转录；必须使用最终播放音轨，不能把背景音乐当口播。
- 订阅预览仅供每日原文审阅，不参与观点和标的分析。
- 采集时间筛选必须以 `created_at` / `published_at` 为准，而不是 `collected_at`。
- 入库必须去重。
