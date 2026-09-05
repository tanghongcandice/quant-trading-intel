# Changelog

## v1.2 — 2026-09-05

- 每日五次增量采集入口：`scripts/run_daily_collection.sh`，北京时间 00:00、08:00、11:00、16:00、20:00。调度需在运行机器另行配置。
- X 恢复 x-crawler helper，保存 helper 纯代码快照供迁移。
- Discord、Substack 恢复 exporter/helper 采集路径，保留作者范围、回复上下文、翻译及静态图片处理。
- Discord 增加历史覆盖检查、分段检查点及作者校验，避免空结果误报成功和回复头像导致作者误归属。
- 以主库已入库数据判断 Discord 漏项；新增并发锁和中断状态，防止未入库内容被跳过。
- Discord 英文内容缺少中文翻译时进入待复核文件，不冒充入库成功；仍需 Codex 完成复核。
- 更新抖音音轨处理与预览隔离流程。
- 清理 Discord 正文的界面时间杂质，隐藏无正文、无静态图片的消息（含 GIF-only）。
- 微信公众号仅处理用户提供链接，保留财经段落；修正新页面发布时间和文章 ID 解析。

### 数据与迁移

不包含 `.env`、Cookie、Token、浏览器 profile、数据库、采集原文、图片或运行日志。标签保存代码，不是实时数据备份。

X helper 快照为 `vendor/x-crawler/scripts/xcrawl.py`。新机器安装 Playwright 和 Chrome 后，将 `X_CRAWLER_SKILL_SCRIPT` 设为该文件的绝对路径，通过项目 Python 运行 `scripts/xcrawl_project.py login` 自行登录。当前机器默认 helper 路径不变。

历史 repair 回补脚本依赖本地审阅产物，不属于每日任务入口，勿盲目重复运行。
