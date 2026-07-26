from __future__ import annotations

from typing import Any, Literal

SourceType = Literal["x", "discord", "substack"]
Sentiment = Literal["看涨", "看跌", "中性", "观望"]


def preview_text(text: str | None, limit: int = 240) -> str:
    clean = " ".join((text or "").split())
    return clean[:limit]


def compact_item(row: dict[str, Any], entities: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "collected_at": row["collected_at"],
        "source": {
            "type": row["source_type"],
            "id": row["source_id"],
            "name": row["source_name"],
        },
        "author": {
            "handle": row["author_handle"],
            "display_name": row["author_display_name"],
        },
        "title": row["title"],
        "content_preview": preview_text(row["content_text"]),
        "external_url": row["external_url"],
        "tickers": sorted(
            {
                entity["normalized_value"]
                for entity in entities or []
                if entity.get("entity_type") == "ticker"
            }
        ),
    }
