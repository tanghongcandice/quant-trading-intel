from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import get_settings
from app.services.ingestion_service import import_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Import information_item.v1 JSONL into the database.")
    parser.add_argument("--jsonl", required=True, type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--mode", default="manual_import")
    args = parser.parse_args()
    settings = get_settings(str(args.db) if args.db else None)
    result = import_jsonl(settings.db_path, args.jsonl.resolve(), args.run_id, args.mode)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
