from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .utils import canonical_json, normalize_url, sha256_text, utc_now_iso


class StateStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.ensure_schema()

    def close(self) -> None:
        self.conn.close()

    def ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                config_path TEXT,
                summary_json TEXT
            );

            CREATE TABLE IF NOT EXISTS source_runs (
                run_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                config_hash TEXT,
                raw_dir TEXT,
                item_count INTEGER DEFAULT 0,
                new_count INTEGER DEFAULT 0,
                duplicate_count INTEGER DEFAULT 0,
                error TEXT,
                PRIMARY KEY (run_id, source_id, attempt)
            );

            CREATE TABLE IF NOT EXISTS items (
                dedupe_key TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                external_id TEXT,
                external_url TEXT,
                content_hash TEXT,
                created_at TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                first_run_id TEXT NOT NULL,
                last_run_id TEXT NOT NULL,
                raw_item_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_items_source ON items(source_type, source_id);
            CREATE INDEX IF NOT EXISTS idx_items_created ON items(created_at);
            CREATE INDEX IF NOT EXISTS idx_source_runs_run ON source_runs(run_id);
            """
        )
        self.conn.commit()

    def start_run(self, run_id: str, config_path: Path) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO runs(run_id, started_at, status, config_path)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, utc_now_iso(), "running", str(config_path)),
        )
        self.conn.commit()

    def finish_run(self, run_id: str, status: str, summary: dict[str, Any]) -> None:
        self.conn.execute(
            """
            UPDATE runs
            SET finished_at = ?, status = ?, summary_json = ?
            WHERE run_id = ?
            """,
            (utc_now_iso(), status, canonical_json(summary), run_id),
        )
        self.conn.commit()

    def start_source(
        self,
        *,
        run_id: str,
        source_id: str,
        source_type: str,
        attempt: int,
        config_hash: str,
        raw_dir: Path,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO source_runs(
                run_id, source_id, source_type, attempt, status, started_at, config_hash, raw_dir
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, source_id, source_type, attempt, "running", utc_now_iso(), config_hash, str(raw_dir)),
        )
        self.conn.commit()

    def finish_source(
        self,
        *,
        run_id: str,
        source_id: str,
        attempt: int,
        status: str,
        item_count: int,
        new_count: int,
        duplicate_count: int,
        error: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE source_runs
            SET finished_at = ?, status = ?, item_count = ?, new_count = ?, duplicate_count = ?, error = ?
            WHERE run_id = ? AND source_id = ? AND attempt = ?
            """,
            (utc_now_iso(), status, item_count, new_count, duplicate_count, error, run_id, source_id, attempt),
        )
        self.conn.commit()

    def make_dedupe_key(self, item: dict[str, Any]) -> str:
        source_type = item.get("source", {}).get("type") or "unknown"
        source_id = item.get("source", {}).get("id") or "unknown"
        external = item.get("external", {})
        external_id = external.get("id")
        external_url = normalize_url(external.get("url"))
        content_hash = item.get("content", {}).get("hash")

        if external_id:
            return f"{source_type}:external_id:{external_id}"
        if external_url:
            return f"{source_type}:url:{external_url}"
        return f"{source_type}:source:{source_id}:content:{content_hash}"

    def upsert_item(self, item: dict[str, Any], run_id: str, seen_at: str) -> tuple[bool, str]:
        dedupe_key = self.make_dedupe_key(item)
        item_id = "itm_" + sha256_text(dedupe_key)[:24]
        item["id"] = item_id
        item.setdefault("ingestion", {})
        item["ingestion"]["dedupe_key"] = dedupe_key

        source = item.get("source", {})
        external = item.get("external", {})
        content = item.get("content", {})
        timestamps = item.get("timestamps", {})
        raw_item_json = canonical_json(item)

        existing = self.conn.execute("SELECT item_id FROM items WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
        if existing:
            self.conn.execute(
                """
                UPDATE items
                SET last_seen_at = ?, last_run_id = ?, raw_item_json = ?
                WHERE dedupe_key = ?
                """,
                (seen_at, run_id, raw_item_json, dedupe_key),
            )
            self.conn.commit()
            return False, existing["item_id"]

        self.conn.execute(
            """
            INSERT INTO items(
                dedupe_key, item_id, source_type, source_id, external_id, external_url,
                content_hash, created_at, first_seen_at, last_seen_at, first_run_id, last_run_id, raw_item_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dedupe_key,
                item_id,
                source.get("type"),
                source.get("id"),
                external.get("id"),
                normalize_url(external.get("url")),
                content.get("hash"),
                timestamps.get("created_at"),
                seen_at,
                seen_at,
                run_id,
                run_id,
                raw_item_json,
            ),
        )
        self.conn.commit()
        return True, item_id

    def counts(self) -> dict[str, Any]:
        items = self.conn.execute("SELECT COUNT(*) AS count FROM items").fetchone()["count"]
        runs = self.conn.execute("SELECT COUNT(*) AS count FROM runs").fetchone()["count"]
        by_source = [
            dict(row)
            for row in self.conn.execute(
                """
                SELECT source_type, source_id, COUNT(*) AS count
                FROM items
                GROUP BY source_type, source_id
                ORDER BY count DESC
                """
            ).fetchall()
        ]
        recent_runs = [
            dict(row)
            for row in self.conn.execute(
                """
                SELECT run_id, started_at, finished_at, status
                FROM runs
                ORDER BY started_at DESC
                LIMIT 10
                """
            ).fetchall()
        ]
        return {"db": str(self.db_path), "items": items, "runs": runs, "by_source": by_source, "recent_runs": recent_runs}
