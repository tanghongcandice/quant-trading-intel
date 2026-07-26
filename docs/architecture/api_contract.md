# API Contract v1

Base URL:

```text
http://localhost:8000/api
```

## GET /items

查询本地信息库。

Example:

```http
GET /api/items?start_at=2026-06-16T00:00:00%2B08:00&end_at=2026-06-20T08:00:00%2B08:00&ticker=MU&limit=50
```

Response:

```json
{
  "items": [
    {
      "id": "itm_xxx",
      "created_at": "2026-06-19T13:11:12Z",
      "source": {
        "type": "x",
        "id": "x_aleabitoreddit",
        "name": "X @aleabitoreddit"
      },
      "author": {
        "handle": "aleabitoreddit",
        "display_name": "Serenity"
      },
      "tickers": ["LPK"],
      "analysis": {
        "theme": "先进封装/玻璃基板",
        "sentiment": "看涨",
        "reason": "TAM 超预期，NASDAQ listing 被讨论"
      },
      "content_preview": "Wow, I completely missed this with $LPK meeting notes...",
      "external_url": "https://x.com/..."
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

## GET /items/{item_id}

获取单条完整信息。

Response:

```json
{
  "item": {
    "schema_version": "information_item.v1"
  },
  "analysis": {},
  "entities": []
}
```

## GET /context/item/{item_id}

获取可复制给 Codex 的上下文。

Query:

| 参数 | 默认值 |
|---|---:|
| author_context_limit | 10 |
| ticker_context_limit | 10 |
| theme_context_limit | 10 |
| format | markdown |

Response:

```json
{
  "item_id": "itm_xxx",
  "format": "markdown",
  "copy_text": "# 数据进阶分析请求\\n...",
  "context": {
    "current_item": {},
    "same_author_items": [],
    "same_ticker_items": [],
    "same_theme_items": []
  }
}
```

## GET /reports/premarket

获取盘前日报。

Example:

```http
GET /api/reports/premarket?report_date=2026-06-20&start_at=2026-06-19T00:00:00%2B08:00&end_at=2026-06-20T08:30:00%2B08:00
```

Response:

```json
{
  "report_version": "premarket_report.v1",
  "report_date": "2026-06-20",
  "market_bias": {
    "view": "看涨",
    "confidence": 0.72,
    "summary": "..."
  },
  "source_tables": [],
  "ticker_view_history": [],
  "data_quality": {}
}
```

## POST /ingestion/run

手动触发采集。

Request:

```json
{
  "mode": "premarket",
  "sources": ["x", "discord", "substack"],
  "window": {
    "start_at": "2026-06-19T00:00:00+08:00",
    "end_at": "2026-06-20T08:30:00+08:00"
  }
}
```

Response:

```json
{
  "run_id": "run_20260620T003000Z",
  "status": "queued"
}
```

## GET /runs

采集任务列表。

Response:

```json
{
  "runs": [
    {
      "id": "run_20260620T003000Z",
      "mode": "premarket",
      "status": "success",
      "started_at": "2026-06-20T00:30:00Z",
      "finished_at": "2026-06-20T00:34:12Z",
      "item_count": 122,
      "error_count": 0
    }
  ]
}
```
