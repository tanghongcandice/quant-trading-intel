import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "packages" / "ingestion_scheduler" / "src"))

from app.jobs.collect_premarket import _requires_codex_review
from ingestion_scheduler.runner import _advance_main_cursor, _cursor_eligible
from ingestion_scheduler.state import StateStore


def discord_item(*, external_id="1542911614054047765", is_new=True, text="Bought Gold XAU"):
    return {
        "source": {"type": "discord", "id": "discord_club500_edgerunner_messages"},
        "external": {"id": external_id},
        "content": {"text": text},
        "raw_payload": {},
        "ingestion": {"is_new": is_new},
    }


class IncrementalDiscordReviewTests(unittest.TestCase):
    def test_scheduler_cursor_survives_final_store_dedupe(self):
        with tempfile.TemporaryDirectory() as directory:
            state = StateStore(Path(directory) / "state.sqlite")
            state.advance_cursor(
                "discord_club500_edgerunner_messages",
                "2026-09-01T09:31:39Z",
                "1544278559462400070",
                "prior_run",
            )
            self.assertEqual(
                state.get_cursor("discord_club500_edgerunner_messages")["last_successful_created_at"],
                "2026-09-01T09:31:39Z",
            )
            state.close()

    def test_successful_collection_advances_main_cursor_without_retained_item(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "main.sqlite"
            db_path.touch()
            item = discord_item()
            item["timestamps"] = {"created_at": "2026-09-01T09:31:39Z"}
            _advance_main_cursor(db_path, "discord_club500_edgerunner_messages", item, "new_run")
            import sqlite3
            with sqlite3.connect(db_path) as db:
                row = db.execute(
                    "select last_successful_created_at,last_successful_external_id from source_cursors"
                ).fetchone()
            self.assertEqual(row, ("2026-09-01T09:31:39Z", "1542911614054047765"))

    def test_context_only_author_does_not_advance_cursor(self):
        source = {"type": "discord", "target_authors": ["Edgerunner"]}
        target_item = discord_item()
        target_item["author"] = {"display_name": "Edgerunner (Magnificent balance)"}
        context_item = discord_item()
        context_item["author"] = {"display_name": "Dalin"}
        self.assertTrue(_cursor_eligible(target_item, source))
        self.assertFalse(_cursor_eligible(context_item, source))

    def test_known_duplicate_never_enters_review(self):
        self.assertFalse(_requires_codex_review(discord_item(is_new=False)))

    def test_new_english_item_enters_review(self):
        self.assertTrue(_requires_codex_review(discord_item(is_new=True)))

    def test_link_only_and_translated_items_skip_review(self):
        self.assertFalse(_requires_codex_review(discord_item(text="https://example.com")))
        item = discord_item()
        item["raw_payload"]["translation"] = {"text": "买入黄金"}
        self.assertFalse(_requires_codex_review(item))


if __name__ == "__main__":
    unittest.main()
