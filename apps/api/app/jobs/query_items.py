from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import get_settings
from app.services.query_service import query_items


def main() -> None:
    parser = argparse.ArgumentParser(description="Query information items.")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--start-at")
    parser.add_argument("--end-at")
    parser.add_argument("--source-type")
    parser.add_argument("--source-id")
    parser.add_argument("--author")
    parser.add_argument("--ticker")
    parser.add_argument("--q")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    settings = get_settings(str(args.db) if args.db else None)
    result = query_items(
        settings.db_path,
        start_at=args.start_at,
        end_at=args.end_at,
        source_type=args.source_type,
        source_id=args.source_id,
        author=args.author,
        ticker=args.ticker,
        q=args.q,
        limit=args.limit,
        offset=args.offset,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
