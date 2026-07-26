from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import get_settings
from app.services.context_service import build_item_context


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Codex-ready context for an item.")
    parser.add_argument("item_id")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()
    settings = get_settings(str(args.db) if args.db else None)
    result = build_item_context(settings.db_path, args.item_id, format=args.format)
    if args.format == "markdown":
        print(result["copy_text"])
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
