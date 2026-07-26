from __future__ import annotations

from typing import Any

from .utils import canonical_json, extract_cashtags, normalize_timestamp, sha256_text, utc_now_iso


SCHEMA_VERSION = "information_item.v1"


def content_hash(title: str | None, text: str | None, html: str | None = None) -> str:
    payload = canonical_json({"title": title or "", "text": text or "", "html": html or ""})
    return sha256_text(payload)


def entity_records_from_text(text: str | None) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for ticker in extract_cashtags(text):
        entities.append(
            {
                "type": "ticker",
                "value": ticker,
                "normalized_value": ticker,
                "confidence": 0.95,
                "source": "regex.cashtag",
                "metadata": {},
            }
        )
    return entities


def build_information_item(
    *,
    source_type: str,
    source_id: str,
    source_name: str,
    collector: str,
    adapter_version: str,
    tags: list[str] | None,
    external_id: str | None,
    external_url: str | None,
    title: str | None,
    content_text: str | None,
    content_html: str | None = None,
    language: str | None = None,
    author: dict[str, Any] | None = None,
    created_at: Any = None,
    collected_at: str | None = None,
    edited_at: Any = None,
    parent_external_id: str | None = None,
    thread_external_id: str | None = None,
    is_reply: bool = False,
    is_repost: bool = False,
    is_quote: bool = False,
    metrics: dict[str, Any] | None = None,
    entities: list[dict[str, Any]] | None = None,
    raw_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    c_hash = content_hash(title, content_text, content_html)
    inferred_entities = entity_records_from_text(content_text)
    all_entities = [*(entities or []), *inferred_entities]
    return {
        "schema_version": SCHEMA_VERSION,
        "id": None,
        "source": {
            "type": source_type,
            "id": source_id,
            "name": source_name,
            "collector": collector,
            "adapter_version": adapter_version,
            "tags": tags or [],
        },
        "external": {
            "id": str(external_id) if external_id not in (None, "") else None,
            "url": external_url,
            "parent_id": str(parent_external_id) if parent_external_id else None,
            "thread_id": str(thread_external_id) if thread_external_id else None,
        },
        "author": author
        or {
            "external_id": None,
            "handle": None,
            "display_name": None,
            "profile_url": None,
            "metadata": {},
        },
        "content": {
            "title": title,
            "text": content_text,
            "html": content_html,
            "language": language,
            "hash": c_hash,
        },
        "timestamps": {
            "created_at": normalize_timestamp(created_at),
            "collected_at": collected_at or utc_now_iso(),
            "edited_at": normalize_timestamp(edited_at),
            "deleted_at": None,
        },
        "relations": {
            "is_reply": is_reply,
            "is_repost": is_repost,
            "is_quote": is_quote,
            "parent_external_id": str(parent_external_id) if parent_external_id else None,
            "thread_external_id": str(thread_external_id) if thread_external_id else None,
        },
        "metrics": metrics or {},
        "entities": all_entities,
        "analysis": None,
        "raw_payload": raw_payload or {},
    }
