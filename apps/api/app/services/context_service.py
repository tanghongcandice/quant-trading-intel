from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.schemas import preview_text
from app.services.query_service import get_item


def _analysis_enabled(row: dict[str, Any]) -> bool:
    try:
        raw = json.loads(row.get("raw_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return True
    return (raw.get("raw_payload") or {}).get("analysis_policy", {}).get("include") is not False


def _translation_text(row: dict[str, Any]) -> str:
    try:
        raw = json.loads(row.get("raw_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return ""
    translation = (raw.get("raw_payload") or {}).get("translation") or {}
    return str(translation.get("text") or "") if isinstance(translation, dict) else str(translation)


def _reply_context(row: dict[str, Any]) -> dict[str, Any] | None:
    try:
        raw = json.loads(row.get("raw_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return None
    context = (raw.get("raw_payload") or {}).get("reply_context")
    return context if isinstance(context, dict) else None


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
    if not _analysis_enabled(current):
        raise PermissionError(f"Item is review-only and cannot enter analysis context: {item_id}")
    author = current.get("author_handle") or current.get("author_display_name")
    current_translation = _translation_text(current)
    current_reply = _reply_context(current)
    reply_lines: list[str] = []
    if current_reply:
        reply_author = current_reply.get("author") or {}
        reply_lines = [
            "",
            "## 被回复消息（仅作上下文，不视为当前作者观点）",
            f"- 作者: {reply_author.get('display_name') or reply_author.get('handle') or 'unknown'}",
            f"- 发布时间: {current_reply.get('timestamp') or '未知'}",
            f"- 链接: {current_reply.get('url') or '无'}",
            "- 原文:",
            f"> {preview_text(current_reply.get('content'), 1200) if current_reply.get('available') else '原回复不可用'}",
        ]

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
        "- 原文:",
        f"> {preview_text(current.get('content_text'), 1200)}",
        *(["- 中文翻译:", f"> {preview_text(current_translation, 1200)}"] if current_translation else []),
        *reply_lines,
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
            "same_author_items": [],
            "same_ticker_items": [],
        },
    }
