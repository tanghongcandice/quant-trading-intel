from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from build_douyin_group import build
from douyin_group_processing_ledger import record, reuse, voice_batches
from ingestion_scheduler.adapters.base import AdapterContext
from ingestion_scheduler.adapters.discord import DiscordAdapter
from ingestion_scheduler.adapters.x import XAdapter


class GroupProcessingLedgerTests(unittest.TestCase):
    def payload(self) -> dict:
        return {
            "group_name": "宇菠萝的认知圈1群",
            "captured_at": "2026-09-07T12:00:00Z",
            "messages": [
                {
                    "index": 2,
                    "time": "12:20",
                    "author": "宇菠萝",
                    "role": "管理员",
                    "text": "12:20\n宇菠萝\n管理员\n3\"",
                    "voice": "第一段。",
                    "duration": "3\"",
                    "images": [{"url": "https://p3.douyinpic.com/img/aweme-avatar/a.webp?x=1"}],
                    "links": [],
                },
                {"index": 1, "voice": "第二段。", "duration": "8\"", "images": [], "links": []},
            ],
            "voice_paragraph_starts": [2],
        }

    def test_fingerprint_ignores_dom_indexes_and_transcript(self) -> None:
        original = self.payload()
        changed = copy.deepcopy(original)
        changed["messages"][0]["index"] = 102
        changed["messages"][1]["index"] = 101
        changed["messages"][0]["voice"] = ""
        changed["messages"][1]["voice"] = ""
        self.assertEqual(voice_batches(original)[0]["fingerprint"], voice_batches(changed)[0]["fingerprint"])

    def test_reuses_only_when_final_item_exists(self) -> None:
        payload = self.payload()
        items = build(payload)
        ledger = {"version": 1, "source_id": "douyin_group_yuboluo_1", "batches": {}}
        self.assertEqual(record(payload, items, ledger)["recorded_batches"], 1)
        blank = copy.deepcopy(payload)
        for row in blank["messages"]:
            row["voice"] = ""
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "db.sqlite"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE information_items(id TEXT PRIMARY KEY)")
            self.assertEqual(reuse(blank, ledger, db)["reused_segments"], 0)
            with sqlite3.connect(db) as conn:
                conn.execute("INSERT INTO information_items(id) VALUES(?)", (items[0]["id"],))
            result = reuse(blank, ledger, db)
        self.assertEqual(result, {"reused_batches": 1, "reused_segments": 2})
        self.assertEqual([row["voice"] for row in blank["messages"]], ["第一段。", "第二段。"])


class StableIdAdapterReuseTests(unittest.TestCase):
    def test_x_and_discord_reuse_validated_static_images(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root / "cached.jpg"
            image.write_bytes(b"cached")
            cached = {"kind": "static_image", "local_path": str(image), "bytes": 6, "source_url": "https://old"}

            def context(lookup):
                return AdapterContext(root, "test", root, root, "2026-09-07T00:00:00Z", False, 10, lookup)

            previous_x = {
                "content": {"text": "same"},
                "raw_payload": {"media": {"static_images": [cached]}},
                "ingestion": {"ledger_item_id": "x-old"},
            }
            with patch(
                "ingestion_scheduler.adapters.x.download_static_images",
                side_effect=AssertionError("X redownloaded an unchanged image"),
            ):
                item = XAdapter()._normalize_tweet(
                    {"id": "x_test", "name": "x", "tags": []},
                    context(lambda _source, _external: previous_x),
                    {"id": "1", "username": "u", "rawContent": "same", "media": {"photos": [{"url": "https://new"}]}},
                )
            self.assertEqual(item["raw_payload"]["processing_ledger"]["media"], "reused")

            previous_discord = {
                "content": {"text": "same"},
                "relations": {"parent_external_id": None},
                "raw_payload": {"media": {"static_images": [cached]}},
                "ingestion": {"ledger_item_id": "d-old"},
            }
            with patch(
                "ingestion_scheduler.adapters.discord.download_static_images",
                side_effect=AssertionError("Discord redownloaded an unchanged image"),
            ):
                item = DiscordAdapter()._normalize_message(
                    {"id": "d_test", "name": "d", "tags": [], "guild_id": "g", "channel_id": "c"},
                    context(lambda _source, _external: previous_discord),
                    {"id": "2", "content": "same", "attachments": [{"url": "https://new/a.jpg", "contentType": "image/jpeg"}]},
                )
            self.assertEqual(item["raw_payload"]["processing_ledger"]["media"], "reused")


if __name__ == "__main__":
    unittest.main()
