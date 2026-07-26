from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.core.db import connect


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a premarket report snapshot.")
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--start-at", required=True)
    parser.add_argument("--end-at", required=True)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--report-html", type=Path)
    parser.add_argument("--item-count", type=int, default=0)
    parser.add_argument("--db", type=Path)
    args = parser.parse_args()

    settings = get_settings(str(args.db) if args.db else None)
    report_id = f"premarket_{args.report_date}"
    report_json = (
        args.report_json.read_text(encoding="utf-8")
        if args.report_json and args.report_json.exists()
        else json.dumps({"report_date": args.report_date}, ensure_ascii=False)
    )
    report_html = (
        args.report_html.read_text(encoding="utf-8")
        if args.report_html and args.report_html.exists()
        else None
    )

    with connect(settings.db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO report_snapshots (
              id, report_type, report_date, start_at, end_at, generated_at,
              report_json, report_html, item_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                "premarket",
                args.report_date,
                args.start_at,
                args.end_at,
                utc_now_iso(),
                report_json,
                report_html,
                args.item_count,
            ),
        )
        conn.commit()
    print(json.dumps({"id": report_id, "db_path": str(settings.db_path), "item_count": args.item_count}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
