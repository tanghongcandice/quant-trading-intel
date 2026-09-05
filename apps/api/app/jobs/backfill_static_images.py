from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from ingestion_scheduler.media import (
    discord_image_candidates,
    download_static_images,
    x_image_candidates,
)


def candidates_for(item: dict[str, Any]) -> list[dict[str, Any]]:
    raw_payload = item.get("raw_payload") or {}
    source_type = str((item.get("source") or {}).get("type") or "")
    if source_type == "x":
        media = raw_payload.get("media") or {}
        if isinstance(media, dict) and "remote" in media:
            media = media.get("remote") or {}
        return x_image_candidates(media)
    if source_type == "discord":
        return discord_image_candidates(raw_payload.get("discord") or {})
    return []


def backfill(db_path: Path, media_root: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    scanned = updated = downloaded = 0
    try:
        rows = conn.execute(
            "SELECT id, source_id, external_id, raw_json FROM information_items WHERE source_type IN ('x', 'discord')"
        ).fetchall()
        with conn:
            for row in rows:
                scanned += 1
                item = json.loads(row["raw_json"])
                candidates = candidates_for(item)
                if not candidates:
                    continue
                images = download_static_images(
                    candidates,
                    media_root=media_root,
                    source_id=row["source_id"],
                    external_id=str(row["external_id"] or row["id"]),
                )
                if not images:
                    continue
                item.setdefault("raw_payload", {})["static_images"] = images
                conn.execute(
                    "UPDATE information_items SET raw_json = ? WHERE id = ?",
                    (json.dumps(item, ensure_ascii=False, sort_keys=True), row["id"]),
                )
                updated += 1
                downloaded += len(images)
    finally:
        conn.close()
    return {"scanned": scanned, "updated_items": updated, "downloaded_images": downloaded}


def main() -> None:
    parser = argparse.ArgumentParser(description="Download static X/Discord images referenced by existing items.")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--media-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(backfill(args.db, args.media_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
