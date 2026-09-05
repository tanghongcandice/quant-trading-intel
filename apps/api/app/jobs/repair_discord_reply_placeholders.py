from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Mark unresolved Discord reply placeholders as unavailable.")
    parser.add_argument("--db", required=True, type=Path)
    args = parser.parse_args()

    connection = sqlite3.connect(args.db)
    updated = 0
    try:
        rows = connection.execute(
            "SELECT id, raw_json FROM information_items WHERE source_type = 'discord'"
        ).fetchall()
        with connection:
            for item_id, raw_json in rows:
                item = json.loads(raw_json or "{}")
                context = (item.get("raw_payload") or {}).get("reply_context")
                if not isinstance(context, dict):
                    continue
                author = context.get("author") or {}
                author_name = author.get("display_name") or author.get("handle")
                if author_name != "消息无法加载" or context.get("id") or context.get("content"):
                    continue
                context["available"] = False
                context["author"] = {
                    "external_id": None,
                    "handle": None,
                    "display_name": None,
                }
                connection.execute(
                    "UPDATE information_items SET raw_json = ? WHERE id = ?",
                    (json.dumps(item, ensure_ascii=False, sort_keys=True), item_id),
                )
                updated += 1
    finally:
        connection.close()
    print(json.dumps({"updated": updated}, ensure_ascii=False))


if __name__ == "__main__":
    main()
