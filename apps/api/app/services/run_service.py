from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.db import connect


def list_runs(db_path: Path, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    with connect(db_path) as conn:
        total_row = conn.execute("SELECT COUNT(*) AS total FROM ingestion_runs").fetchone()
        rows = conn.execute(
            """
            SELECT id, mode, status, started_at, finished_at, source_count, item_count, error_count, summary_json
            FROM ingestion_runs
            ORDER BY started_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    runs = []
    for row in rows:
        doc = dict(row)
        try:
            doc["summary"] = json.loads(doc.pop("summary_json") or "{}")
        except json.JSONDecodeError:
            doc["summary"] = {"raw": doc.pop("summary_json")}
        runs.append(doc)

    return {
        "runs": runs,
        "total": int(total_row["total"] if total_row else 0),
        "limit": limit,
        "offset": offset,
    }
