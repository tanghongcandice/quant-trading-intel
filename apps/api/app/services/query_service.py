from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.db import connect, rows_to_dicts
from app.models.schemas import compact_item


def get_entities_for_items(conn, item_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not item_ids:
        return {}
    placeholders = ",".join("?" for _ in item_ids)
    rows = conn.execute(
        f"""
        SELECT item_id, entity_type, value, normalized_value, confidence, source, metadata_json
        FROM item_entities
        WHERE item_id IN ({placeholders})
        ORDER BY entity_type, normalized_value
        """,
        item_ids,
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {item_id: [] for item_id in item_ids}
    for row in rows:
        doc = dict(row)
        doc["metadata"] = json.loads(doc.pop("metadata_json") or "{}")
        grouped.setdefault(doc["item_id"], []).append(doc)
    return grouped


def query_items(
    db_path: Path,
    *,
    start_at: str | None = None,
    end_at: str | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    author: str | None = None,
    ticker: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    where = []
    params: list[Any] = []
    join = ""

    if start_at:
        where.append("i.created_at >= ?")
        params.append(start_at)
    if end_at:
        where.append("i.created_at <= ?")
        params.append(end_at)
    if source_type:
        where.append("i.source_type = ?")
        params.append(source_type)
    if source_id:
        where.append("i.source_id = ?")
        params.append(source_id)
    if author:
        where.append("(i.author_handle = ? OR i.author_display_name = ?)")
        params.extend([author, author])
    if ticker:
        join += " JOIN item_entities e ON e.item_id = i.id "
        where.append("e.entity_type = 'ticker' AND e.normalized_value = ?")
        params.append(ticker.upper())
    if q:
        join += " JOIN information_items_fts f ON f.item_id = i.id "
        where.append("information_items_fts MATCH ?")
        params.append(q)

    where_sql = "WHERE " + " AND ".join(where) if where else ""
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    with connect(db_path) as conn:
        total_row = conn.execute(
            f"SELECT COUNT(DISTINCT i.id) AS total FROM information_items i {join} {where_sql}",
            params,
        ).fetchone()
        rows = conn.execute(
            f"""
            SELECT DISTINCT i.*
            FROM information_items i
            {join}
            {where_sql}
            ORDER BY i.created_at DESC, i.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        docs = rows_to_dicts(rows)
        entities = get_entities_for_items(conn, [doc["id"] for doc in docs])

    return {
        "items": [compact_item(doc, entities.get(doc["id"], [])) for doc in docs],
        "total": int(total_row["total"] if total_row else 0),
        "limit": limit,
        "offset": offset,
    }


def get_item(db_path: Path, item_id: str) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM information_items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        entities = get_entities_for_items(conn, [item_id]).get(item_id, [])
        analysis = conn.execute("SELECT * FROM item_analysis WHERE item_id = ?", (item_id,)).fetchone()
    return {
        "item": json.loads(item["raw_json"]),
        "db_record": item,
        "entities": entities,
        "analysis": dict(analysis) if analysis else None,
    }
