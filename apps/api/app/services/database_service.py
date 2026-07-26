from __future__ import annotations

from pathlib import Path

from app.core.db import connect, execute_script


def schema_path(project_root: Path) -> Path:
    return project_root / "packages" / "shared" / "database_schema.sql"


def init_database(db_path: Path, project_root: Path) -> dict:
    sql = schema_path(project_root).read_text(encoding="utf-8")
    with connect(db_path) as conn:
        execute_script(conn, sql)
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name"
            ).fetchall()
        ]
    return {"db_path": str(db_path), "tables": tables}
