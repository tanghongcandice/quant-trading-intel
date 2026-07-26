from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import get_settings
from app.services.database_service import init_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize quant intelligence SQLite database.")
    parser.add_argument("--db", type=Path)
    args = parser.parse_args()
    settings = get_settings(str(args.db) if args.db else None)
    result = init_database(settings.db_path, settings.project_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
