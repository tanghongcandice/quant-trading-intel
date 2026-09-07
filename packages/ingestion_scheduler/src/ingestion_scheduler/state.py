from __future__ import annotations

import json
import sqlite3
import re
import unicodedata
from pathlib import Path
from typing import Any

from .utils import canonical_json, normalize_url, sha256_text, utc_now_iso


class StateStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._content_index_cache: dict[tuple[str, ...], dict[str, dict[str, Any]]] = {}
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

            -- Independent ingestion watermark.  Browser snapshots are
            -- immutable audit artifacts and must never be used as the
            -- incremental cutoff.
            CREATE TABLE IF NOT EXISTS source_cursors (
                source_id TEXT PRIMARY KEY,
                last_successful_created_at TEXT,
                last_successful_external_id TEXT,
                updated_at TEXT NOT NULL,
                run_id TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def get_cursor(self, source_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM source_cursors WHERE source_id = ?", (source_id,)).fetchone()
        return dict(row) if row else None

    def get_processed_item(self, source_id: str, external_id: str) -> dict[str, Any] | None:
        """Return the last successfully normalized item for early work reuse."""
        if not source_id or not external_id:
            return None
        row = self.conn.execute(
            """SELECT item_id, content_hash, last_seen_at, raw_item_json
               FROM items WHERE source_id = ? AND external_id = ?
               ORDER BY last_seen_at DESC LIMIT 1""",
            (source_id, external_id),
        ).fetchone()
        if not row:
            return None
        try:
            item = json.loads(row["raw_item_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        item.setdefault("ingestion", {})["ledger_item_id"] = row["item_id"]
        item["ingestion"]["ledger_last_seen_at"] = row["last_seen_at"]
        return item

    def advance_cursor(self, source_id: str, created_at: str | None, external_id: str | None, run_id: str) -> None:
        if not created_at:
            return
        current = self.get_cursor(source_id)
        # Watermarks are monotonic; an old/partial snapshot can never move
        # the cursor backwards.
        if current and (current.get("last_successful_created_at") or "") >= created_at:
            return
        self.conn.execute(
            """INSERT INTO source_cursors(source_id,last_successful_created_at,last_successful_external_id,updated_at,run_id)
               VALUES(?,?,?,?,?)
               ON CONFLICT(source_id) DO UPDATE SET
                 last_successful_created_at=excluded.last_successful_created_at,
                 last_successful_external_id=excluded.last_successful_external_id,
                 updated_at=excluded.updated_at, run_id=excluded.run_id""",
            (source_id, created_at, external_id, utc_now_iso(), run_id),
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

    def find_content_duplicate(self, item: dict[str, Any], source_ids: list[str]) -> dict[str, Any] | None:
        """Find an exact normalized-text duplicate in selected sources."""
        # Discord cross-post decisions require the final database, timestamps,
        # media and reply context. State-only text matching loses distinct trades.
        if item.get('source', {}).get('type') == 'discord':
            return None
        if not source_ids:
            return None
        text = str((item.get("content") or {}).get("text") or "")
        normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()
        if not normalized:
            return None
        cache_key = tuple(sorted(source_ids))
        index = self._content_index_cache.get(cache_key)
        if index is None:
            placeholders = ",".join("?" for _ in source_ids)
            rows = self.conn.execute(
                f"SELECT item_id, source_id, external_id, raw_item_json FROM items WHERE source_id IN ({placeholders})",
                tuple(source_ids),
            ).fetchall()
            index = {}
            for row in rows:
                try:
                    payload = json.loads(row["raw_item_json"] or "{}")
                    stored = str((payload.get("content") or {}).get("text") or "")
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                key = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", stored)).strip().casefold()
                if key:
                    index.setdefault(
                        key,
                        {"item_id": row["item_id"], "source_id": row["source_id"], "external_id": row["external_id"]},
                    )
            self._content_index_cache[cache_key] = index
        return index.get(normalized)

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
            self._invalidate_content_indexes(str(source.get("id") or ""))
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
        self._invalidate_content_indexes(str(source.get("id") or ""))
        return True, item_id

    def _invalidate_content_indexes(self, source_id: str) -> None:
        if not source_id:
            return
        for key in [key for key in self._content_index_cache if source_id in key]:
            self._content_index_cache.pop(key, None)

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
