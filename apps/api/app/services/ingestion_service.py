from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.db import connect


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def item_record(item: dict[str, Any], run_id: str) -> tuple:
    source = item.get("source") or {}
    external = item.get("external") or {}
    author = item.get("author") or {}
    content = item.get("content") or {}
    timestamps = item.get("timestamps") or {}
    return (
        item["id"],
        item.get("schema_version", "information_item.v1"),
        source.get("type"),
        source.get("id"),
        source.get("name"),
        source.get("collector"),
        external.get("id"),
        external.get("url"),
        author.get("handle"),
        author.get("display_name"),
        content.get("title"),
        content.get("text"),
        content.get("hash"),
        content.get("language"),
        timestamps.get("created_at"),
        timestamps.get("collected_at"),
        json.dumps(item, ensure_ascii=False, sort_keys=True),
        run_id,
    )


def entity_records(item: dict[str, Any]) -> list[tuple]:
    records: list[tuple] = []
    for entity in item.get("entities") or []:
        if not entity.get("type") or not entity.get("normalized_value"):
            continue
        records.append(
            (
                item["id"],
                entity.get("type"),
                entity.get("value") or entity.get("normalized_value"),
                entity.get("normalized_value"),
                entity.get("confidence", 1.0),
                entity.get("source"),
                json.dumps(entity.get("metadata") or {}, ensure_ascii=False, sort_keys=True),
            )
        )
    return records


def import_jsonl(db_path: Path, jsonl_path: Path, run_id: str | None = None, mode: str = "manual_import") -> dict[str, Any]:
    items = read_jsonl(jsonl_path)
    actual_run_id = run_id or "run_import_" + utc_now_iso().replace("-", "").replace(":", "").replace("Z", "Z")
    started_at = utc_now_iso()
    inserted = 0
    skipped = 0
    entity_count = 0

    with connect(db_path) as conn:
        # Watermark is separate from raw browser snapshots and advances only
        # after a successful import transaction.
        conn.execute("""CREATE TABLE IF NOT EXISTS source_cursors (
            source_id TEXT PRIMARY KEY,
            last_successful_created_at TEXT,
            last_successful_external_id TEXT,
            updated_at TEXT NOT NULL,
            run_id TEXT NOT NULL
        )""")
        conn.execute(
            """
            INSERT OR REPLACE INTO ingestion_runs
            (id, mode, status, started_at, source_count, item_count, error_count, summary_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                actual_run_id,
                mode,
                "running",
                started_at,
                len({(item.get("source") or {}).get("id") for item in items}),
                0,
                0,
                "{}",
            ),
        )
        for item in items:
            before = conn.total_changes
            conn.execute(
                """
                INSERT OR IGNORE INTO information_items (
                  id, schema_version, source_type, source_id, source_name, collector,
                  external_id, external_url, author_handle, author_display_name,
                  title, content_text, content_hash, language,
                  created_at, collected_at, raw_json, run_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                item_record(item, actual_run_id),
            )
            if conn.total_changes == before:
                skipped += 1
                continue

            inserted += 1
            records = entity_records(item)
            entity_count += len(records)
            conn.executemany(
                """
                INSERT INTO item_entities (
                  item_id, entity_type, value, normalized_value, confidence, source, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                records,
            )

            content = item.get("content") or {}
            source = item.get("source") or {}
            author = item.get("author") or {}
            conn.execute(
                """
                INSERT INTO information_items_fts (item_id, title, content_text, author_handle, source_name)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    content.get("title"),
                    content.get("text"),
                    author.get("handle") or author.get("display_name"),
                    source.get("name"),
                ),
            )

        # A referenced Discord parent is retained for reply context, but must
        # not appear as a standalone feed item. Mark it after importing all
        # items so this works whether the parent is new or already stored.
        for item in items:
            relations = item.get("relations") or {}
            parent_external_id = relations.get("parent_external_id")
            source = item.get("source") or {}
            if not parent_external_id or source.get("type") != "discord":
                continue
            parent = conn.execute(
                "SELECT id, raw_json FROM information_items WHERE source_id = ? AND external_id = ?",
                (source.get("id"), str(parent_external_id)),
            ).fetchone()
            if not parent:
                continue
            try:
                parent_item = json.loads(parent["raw_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            payload = parent_item.setdefault("raw_payload", {})
            if payload.get("analysis_role") == "reply_context_only":
                continue
            payload["analysis_role"] = "reply_context_only"
            payload["analysis_policy"] = {"include": False, "mode": "context_only"}
            conn.execute(
                "UPDATE information_items SET raw_json = ? WHERE id = ?",
                (json.dumps(parent_item, ensure_ascii=False, sort_keys=True), parent["id"]),
            )

        # Advance watermarks only after every item and relation update has
        # succeeded in this transaction.
        finished_at = utc_now_iso()
        by_source: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            sid = (item.get("source") or {}).get("id")
            if sid:
                by_source.setdefault(str(sid), []).append(item)
        for sid, source_items in by_source.items():
            dated = [i for i in source_items if (i.get("timestamps") or {}).get("created_at")]
            if not dated:
                continue
            latest = max(dated, key=lambda i: str((i.get("timestamps") or {}).get("created_at")))
            created = str((latest.get("timestamps") or {}).get("created_at"))
            current = conn.execute("SELECT last_successful_created_at FROM source_cursors WHERE source_id = ?", (sid,)).fetchone()
            if current and (current[0] or "") >= created:
                continue
            conn.execute(
                """INSERT INTO source_cursors(source_id,last_successful_created_at,last_successful_external_id,updated_at,run_id)
                   VALUES(?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET
                   last_successful_created_at=excluded.last_successful_created_at,
                   last_successful_external_id=excluded.last_successful_external_id,
                   updated_at=excluded.updated_at, run_id=excluded.run_id""",
                (sid, created, (latest.get("external") or {}).get("id"), finished_at, actual_run_id),
            )

        summary = {
            "jsonl_path": str(jsonl_path),
            "db_path": str(db_path),
            "run_id": actual_run_id,
            "read_items": len(items),
            "inserted_items": inserted,
            "skipped_duplicates": skipped,
            "inserted_entities": entity_count,
        }
        conn.execute(
            """
            UPDATE ingestion_runs
            SET status = ?, finished_at = ?, item_count = ?, error_count = ?, summary_json = ?
            WHERE id = ?
            """,
            ("success", finished_at, inserted, 0, json.dumps(summary, ensure_ascii=False, sort_keys=True), actual_run_id),
        )
        conn.commit()

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Import information_item.v1 JSONL into SQLite.")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--jsonl", required=True, type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--mode", default="manual_import")
    args = parser.parse_args()
    print(json.dumps(import_jsonl(args.db, args.jsonl, args.run_id, args.mode), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
