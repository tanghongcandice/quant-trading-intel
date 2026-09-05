from __future__ import annotations

import json
from typing import Any, Literal

SourceType = Literal["x", "discord", "substack", "douyin", "wechat"]
Sentiment = Literal["看涨", "看跌", "中性", "观望"]


def preview_text(text: str | None, limit: int = 240) -> str:
    clean = " ".join((text or "").split())
    return clean[:limit]


def compact_item(row: dict[str, Any], entities: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    market = infer_market(row)
    try:
        raw = json.loads(row.get("raw_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        raw = {}
    raw_payload = raw.get("raw_payload") or {}
    analysis_policy = raw_payload.get("analysis_policy") or {"include": True, "mode": "analysis"}
    media = raw_payload.get("static_images") or (raw_payload.get("media") or {}).get("static_images") or []
    translation = raw_payload.get("translation") or None
    summary = raw_payload.get("summary") or None
    relations = raw.get("relations") or {}
    reply_context = raw_payload.get("reply_context") or None
    return {
        "id": row["id"],
        "market": market,
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
        "content_text": row["content_text"],
        "language": row.get("language"),
        "translation": translation,
        "summary": summary,
        "relations": relations,
        "reply_context": reply_context,
        "external_url": row["external_url"],
        "analysis_policy": analysis_policy,
        "review_only": analysis_policy.get("include") is False,
        "media": media,
        "tickers": sorted(
            {
                entity["normalized_value"]
                for entity in entities or []
                if entity.get("entity_type") == "ticker"
            }
        ),
    }


def infer_market(row: dict[str, Any]) -> str:
    try:
        raw = json.loads(row.get("raw_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        raw = {}
    explicit = str(raw.get("market") or raw.get("raw_payload", {}).get("market") or "").lower()
    if explicit in {"cn", "a", "a_share", "ashare", "china"}:
        return "cn"
    tags = {str(tag).lower() for tag in raw.get("source", {}).get("tags", [])}
    if tags & {"market:cn", "a_share", "ashare"}:
        return "cn"
    source_type = str(row.get("source_type") or "").lower()
    source_id = str(row.get("source_id") or "").lower()
    if source_type in {"douyin", "wechat"} or "jiujiujiucai" in source_id or "caitangping" in source_id:
        return "cn"
    return "us"
