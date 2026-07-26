# 盘前信息库前端

这是量化交易信息系统的前端第一版原型，严格按 `outputs/quant_trading_architecture/frontend_backend_architecture.md` 的前端需求实现。

## 已实现

- 时间窗口筛选：全部、今天、近 24 小时、近 3 天、近 7 天、自定义开始/结束时间。
- 多维筛选：来源、作者、标的、题材、观点、全文搜索。
- 信息流表格：按发布时间倒序展示本地 `information_item.v1` 数据。
- 按标的聚合：随筛选条件实时变化。
- 单条数据进阶分析：点击 `分析` 打开右侧上下文抽屉。
- 复制给 Codex：生成包含当前信息、同作者、同标的、同题材上下文的 Markdown。
- 复制原始 JSON：方便排查数据库字段。

## 数据模式

后端不可用时，当前版本使用不含真实采集内容的静态示例数据：

```text
apps/web/data/sample_items.js
```

本地真实采集数据可以继续保存在以下文件，但该文件已被 Git 忽略，不会进入公开仓库：

```text
apps/web/data/high_quality_items.js
```

前端会优先请求 `/api/items` 和 `/api/context/item/{item_id}`；API 不可用时才显示示例数据。

## 打开方式

直接打开：

```text
apps/web/index.html
```

或在允许本地端口的环境中运行：

```bash
cd apps/web
python3 -m http.server 8000 --bind 127.0.0.1
```
