from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill resolved Discord reply context from a browser snapshot.")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--guild-id", required=True)
    parser.add_argument("--channel-id", required=True)
    args = parser.parse_args()

    payload = json.loads(args.snapshot.read_text(encoding="utf-8"))
    messages = payload.get("messages") if isinstance(payload, dict) else payload
    resolved = {}
    for message in messages or []:
        reference = message.get("reference") or {}
        parent = message.get("referencedMessage") or {}
        parent_id = str(reference.get("messageId") or parent.get("id") or "")
        if message.get("id") and parent_id and parent.get("content"):
            resolved[str(message["id"])] = (message, parent_id, parent)

    connection = sqlite3.connect(args.db)
    updated = 0
    try:
        with connection:
            for external_id, (message, parent_id, parent) in resolved.items():
                row = connection.execute(
                    "SELECT id, raw_json FROM information_items WHERE source_id = ? AND external_id = ?",
                    (args.source_id, external_id),
                ).fetchone()
                if not row:
                    continue
                item = json.loads(row[1])
                author = parent.get("author") or {}
                item.setdefault("relations", {})["is_reply"] = True
                item["relations"]["parent_external_id"] = parent_id
                raw_payload = item.setdefault("raw_payload", {})
                raw_payload["discord"] = message
                raw_payload["reply_context"] = {
                    "id": parent_id,
                    "available": True,
                    "url": f"https://discord.com/channels/{args.guild_id}/{args.channel_id}/{parent_id}",
                    "author": {
                        "external_id": author.get("id"),
                        "handle": author.get("name"),
                        "display_name": author.get("displayName") or author.get("name"),
                    },
                    "content": parent.get("content"),
                    "timestamp": parent.get("timestamp"),
                    "static_images": [],
                    "analysis_role": "reply_context_only",
                }
                connection.execute(
                    "UPDATE information_items SET raw_json = ? WHERE id = ?",
                    (json.dumps(item, ensure_ascii=False, sort_keys=True), row[0]),
                )
                updated += 1
    finally:
        connection.close()
    print(json.dumps({"resolved_in_snapshot": len(resolved), "updated": updated}, ensure_ascii=False))


if __name__ == "__main__":
    main()
