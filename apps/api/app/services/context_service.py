from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.db import connect
from app.models.schemas import preview_text
from app.services.query_service import get_entities_for_items, get_item


def _brief(row: dict[str, Any], entities: list[dict[str, Any]]) -> str:
    tickers = sorted({e["normalized_value"] for e in entities if e.get("entity_type") == "ticker"})
    author = row.get("author_handle") or row.get("author_display_name") or "unknown"
    source = row.get("source_name") or row.get("source_id")
    return (
        f"- {row['created_at']} | {source} | {author} | "
        f"标的: {', '.join(tickers) or '无'}\n"
        f"  {preview_text(row.get('content_text'), 320)}"
    )


def build_item_context(
    db_path: Path,
    item_id: str,
    *,
    author_context_limit: int = 10,
    ticker_context_limit: int = 10,
    format: str = "markdown",
) -> dict[str, Any]:
    detail = get_item(db_path, item_id)
    if not detail:
        raise KeyError(f"Item not found: {item_id}")

    current = detail["db_record"]
    current_entities = detail["entities"]
    tickers = sorted({e["normalized_value"] for e in current_entities if e.get("entity_type") == "ticker"})
    author = current.get("author_handle") or current.get("author_display_name")

    with connect(db_path) as conn:
        author_rows = []
        if author:
            author_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT * FROM information_items
                    WHERE id != ? AND (author_handle = ? OR author_display_name = ?)
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (item_id, author, author, author_context_limit),
                ).fetchall()
            ]

        ticker_rows: list[dict[str, Any]] = []
        if tickers:
            placeholders = ",".join("?" for _ in tickers)
            ticker_rows = [
                dict(row)
                for row in conn.execute(
                    f"""
                    SELECT DISTINCT i.*
                    FROM information_items i
                    JOIN item_entities e ON e.item_id = i.id
                    WHERE i.id != ? AND e.entity_type = 'ticker' AND e.normalized_value IN ({placeholders})
                    ORDER BY i.created_at DESC
                    LIMIT ?
                    """,
                    [item_id, *tickers, ticker_context_limit],
                ).fetchall()
            ]

        entity_map = get_entities_for_items(conn, [r["id"] for r in [current, *author_rows, *ticker_rows]])

    lines = [
        "# 数据进阶分析请求",
        "",
        "请基于以下本地数据库上下文，分析这条信息对盘前交易的意义。",
        "",
        "## 当前信息",
        f"- item_id: {item_id}",
        f"- 发布时间: {current['created_at']}",
        f"- 来源: {current['source_name']}",
        f"- 作者: {author or 'unknown'}",
        f"- 链接: {current.get('external_url') or '无'}",
        f"- 标的: {', '.join(tickers) or '无'}",
        "- 原文:",
        f"> {preview_text(current.get('content_text'), 1200)}",
        "",
        "## 同作者近似上下文",
        *[_brief(row, entity_map.get(row["id"], [])) for row in author_rows],
        "",
        "## 同标的近似上下文",
        *[_brief(row, entity_map.get(row["id"], [])) for row in ticker_rows],
        "",
        "## 希望你输出",
        "1. 这条信息是否构成交易信号",
        "2. 看涨/看跌/中性",
        "3. 证据链",
        "4. 风险和反证",
        "5. 如果纳入盘前日报，应该放在哪个题材和标的下",
    ]
    copy_text = "\n".join(lines)

    return {
        "item_id": item_id,
        "format": format,
        "copy_text": copy_text,
        "context": {
            "current_item": detail["item"],
            "same_author_items": [json.loads(row["raw_json"]) for row in author_rows],
            "same_ticker_items": [json.loads(row["raw_json"]) for row in ticker_rows],
        },
    }
