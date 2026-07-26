# 每日盘前日报设计规范

## 目标

每日盘前日报不是简单的信息列表，而是把 X、Discord、Substack 等原始信息统一压缩成可交易的证据链：

1. 先判断大盘和核心题材的方向。
2. 再把每个信息源按大盘/题材/标的聚合。
3. 每条观点必须带发布时间、证据、相关原句和风险。
4. 发布时间是核心权重变量，越新的高质量消息权重越高。

## 输入

输入为 `information_item.v1` JSONL，每条信息至少依赖这些字段：

```json
{
  "schema_version": "information_item.v1",
  "source": {
    "type": "x|discord|substack",
    "id": "source_id",
    "name": "source_name",
    "collector": "crawler_name",
    "tags": []
  },
  "external": {
    "id": "platform_id",
    "url": "source_url"
  },
  "author": {
    "handle": "author_handle",
    "display_name": "author_name"
  },
  "content": {
    "title": "optional_title",
    "text": "raw_text"
  },
  "timestamps": {
    "created_at": "published_or_created_at",
    "collected_at": "collected_at"
  },
  "entities": [
    {
      "type": "ticker",
      "normalized_value": "MU"
    }
  ],
  "metrics": {},
  "raw_payload": {}
}
```

## 输出结构

```json
{
  "report_version": "premarket_report.v1",
  "report_date": "YYYY-MM-DD",
  "collection_window": {
    "start": "ISO-8601",
    "end": "ISO-8601",
    "timezone": "Asia/Shanghai"
  },
  "market_bias": {
    "view": "看涨|看跌|中性|观望",
    "confidence": 0.0,
    "summary": "一句话方向判断",
    "evidence": [
      {
        "source": "source_id",
        "author": "author",
        "created_at": "ISO-8601",
        "original_text": "短原文"
      }
    ],
    "risks": []
  },
  "fundamental_analysis": [
    {
      "theme": "宏观流动性",
      "view": "看涨",
      "reason": "为什么",
      "evidence_originals": [],
      "risks": []
    }
  ],
  "source_tables": [
    {
      "source_name": "X @haochihaochiaaa",
      "source_type": "x",
      "rows": [
        {
          "题材": "AI 半导体",
          "标的": "AVGO",
          "观点": "看涨",
          "具体标的": "AVGO（未涨）",
          "理由": "380-390 买入区间，持有到历史新高",
          "风险": "若高位追涨，回撤时容易被套",
          "相关原句": "Buy avgo 380-390 hold until all time high"
        }
      ]
    }
  ],
  "ticker_view_history": [
    {
      "ticker": "AMD",
      "history": [
        "06-19: 短线观点...",
        "06-18: ..."
      ]
    }
  ],
  "data_quality": {
    "source_status": [],
    "missing_or_partial": [],
    "warnings": []
  }
}
```

## 表格字段定义

| 字段 | 定义 | 生成规则 |
|---|---|---|
| 题材 | 观点所在的投资主题 | 由关键词、ticker 聚类和作者上下文生成，例如宏观流动性、AI 半导体、Memory、Photonics、软件/SaaS |
| 标的 | 聚合主标的或大盘 | 有明确 ticker 用 ticker；没有具体 ticker 时用“大盘”“AI硬件链”等 |
| 观点 | 看涨/看跌/中性/观望 | 买入、持有、undervalued、supply constrained 为看涨；sell、lock profit、weak、overvalued 为看跌或中性 |
| 具体标的 | 原文提到的标的，并注明已涨/未涨；未提 ticker 时 AI 补充 | 例如 `MU（已涨）`、`AVGO（未涨）`、`QQQ（AI补充标的）` |
| 理由 | 把原文观点转成交易理由 | 必须能回指到相关原句 |
| 风险 | 原文风险或 AI 补充的交易风险 | 若无明确风险，填“未提及；需用行情/估值验证” |
| 相关原句 | 短原文证据 | 保留短摘录，不贴长文全文 |

## “已涨/未涨”判定规则

第一版日报先用原文和行情模块双层判定：

1. 原文明确说 `up`, `tripled`, `ATH`, `+xx%`, `已经涨`, `目标已到`, `lock profit`：标记为 `已涨`。
2. 原文说 `undervalued`, `market missed`, `buy`, `hold until ATH`, `should recover`, `support`：标记为 `未涨` 或 `未涨/待兑现`。
3. 原文说已经涨很多但仍看多：标记为 `已涨但仍看多`。
4. 没有提到具体标的，由 AI 补充 ETF 或代表性标的，格式为 `QQQ（AI补充标的）`。
5. 生产环境建议接行情模块，用 `source_time_price -> premarket_price` 判断真实涨跌，避免只靠文本。

## 权重设计

建议用于排序和观点合成：

| 因子 | 权重 |
|---|---:|
| 来源质量：Discord 交易指令 | 1.00 |
| 来源质量：Substack 长文框架 | 0.85 |
| 来源质量：X 原创帖 | 0.75 |
| 发布时间：6 小时内 | 1.00 |
| 发布时间：24 小时内 | 0.85 |
| 发布时间：3 天内 | 0.60 |
| 是否有明确标的/价格/操作 | +0.15 |
| 是否只是回复闲聊 | -0.25 |
| 是否有明确风险 | +0.05 |

## 日报版式

1. 标题：`YYYY-MM-DD 美股盘前日报`
2. 数据覆盖：来源数、观点数、时间窗口、缺口提醒
3. 一句话总览：大盘偏向、主线、风险
4. 基本面分析：大盘/题材方向、证据、原文
5. 信息源表格：按来源分组，表格字段固定
6. 标的历史观点：像截图 2 一样，把重要标的的历史观点串起来
7. 风险和数据质量：接口缺口、Discord 是否完整、行情是否接入
