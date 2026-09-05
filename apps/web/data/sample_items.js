window.__HIGH_QUALITY_ITEMS__ = [
  {
    "schema_version": "information_item.v1",
    "id": "sample_x_tsla_001",
    "source": {
      "id": "sample_x_watchlist",
      "type": "x",
      "name": "X 示例观察列表",
      "collector": "x-browser-session",
      "tags": ["sample", "premarket"]
    },
    "external": {"id": "sample-001", "url": ""},
    "author": {"handle": "sample_analyst", "display_name": "示例分析员"},
    "content": {
      "title": null,
      "text": "$TSLA 交付预期改善，盘前成交量同步放大；若开盘后量价继续确认，短线偏多。",
      "language": "zh",
      "hash": "sample-hash-001"
    },
    "timestamps": {
      "created_at": "2026-06-19T11:20:00Z",
      "collected_at": "2026-06-19T11:25:00Z",
      "edited_at": null,
      "deleted_at": null
    },
    "entities": [
      {"type": "ticker", "value": "TSLA", "normalized_value": "TSLA", "confidence": 1, "source": "sample"}
    ],
    "metrics": {"like_count": 42, "reply_count": 8},
    "relations": {},
    "analysis": null,
    "raw_payload": {"sample": true}
  },
  {
    "schema_version": "information_item.v1",
    "id": "sample_substack_macro_001",
    "source": {
      "id": "sample_substack_macro",
      "type": "substack",
      "name": "Substack 示例宏观通讯",
      "collector": "substack-crawler",
      "tags": ["sample", "premarket", "longform"]
    },
    "external": {"id": "sample-002", "url": ""},
    "author": {"handle": "sample_macro", "display_name": "示例宏观作者"},
    "content": {
      "title": "利率路径与成长股估值",
      "text": "长端利率若继续上行，QQQ 的估值扩张可能受压。当前结论偏谨慎，需要等待通胀数据确认。",
      "language": "zh",
      "hash": "sample-hash-002"
    },
    "timestamps": {
      "created_at": "2026-06-18T22:10:00Z",
      "collected_at": "2026-06-19T00:05:00Z",
      "edited_at": null,
      "deleted_at": null
    },
    "entities": [
      {"type": "ticker", "value": "QQQ", "normalized_value": "QQQ", "confidence": 1, "source": "sample"}
    ],
    "metrics": {},
    "relations": {},
    "analysis": null,
    "raw_payload": {"sample": true}
  },
  {
    "schema_version": "information_item.v1",
    "id": "sample_discord_tsla_001",
    "source": {
      "id": "sample_discord_channel",
      "type": "discord",
      "name": "Discord 示例交易频道",
      "collector": "discord-browser-collector",
      "tags": ["sample", "premarket"]
    },
    "external": {"id": "sample-003", "url": ""},
    "author": {"handle": "sample_trader", "display_name": "示例交易员"},
    "content": {
      "title": null,
      "text": "$TSLA 盘前跳空后不追高，关注前高压力和开盘 30 分钟成交量；未确认前保持观望。",
      "language": "zh",
      "hash": "sample-hash-003"
    },
    "timestamps": {
      "created_at": "2026-06-19T12:05:00Z",
      "collected_at": "2026-06-19T12:06:00Z",
      "edited_at": null,
      "deleted_at": null
    },
    "entities": [
      {"type": "ticker", "value": "TSLA", "normalized_value": "TSLA", "confidence": 1, "source": "sample"}
    ],
    "metrics": {},
    "relations": {},
    "analysis": null,
    "raw_payload": {"sample": true}
  },
  {
    "schema_version": "information_item.v1",
    "id": "sample_x_semis_001",
    "source": {
      "id": "sample_x_options",
      "type": "x",
      "name": "X 示例期权观察",
      "collector": "x-browser-session",
      "tags": ["sample", "premarket", "options"]
    },
    "external": {"id": "sample-004", "url": ""},
    "author": {"handle": "sample_options", "display_name": "示例期权观察员"},
    "content": {
      "title": null,
      "text": "$NVDA 与 $AMD 看涨期权成交增加，但隐含波动率偏高；方向看涨，仓位需要控制。",
      "language": "zh",
      "hash": "sample-hash-004"
    },
    "timestamps": {
      "created_at": "2026-06-17T14:30:00Z",
      "collected_at": "2026-06-17T14:33:00Z",
      "edited_at": null,
      "deleted_at": null
    },
    "entities": [
      {"type": "ticker", "value": "NVDA", "normalized_value": "NVDA", "confidence": 1, "source": "sample"},
      {"type": "ticker", "value": "AMD", "normalized_value": "AMD", "confidence": 1, "source": "sample"}
    ],
    "metrics": {"like_count": 18},
    "relations": {},
    "analysis": null,
    "raw_payload": {"sample": true}
  }
];
