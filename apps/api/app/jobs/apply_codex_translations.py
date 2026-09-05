from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def load_translations(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("translations") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("translation file must contain a translations array")
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        item_id = str(record.get("item_id") or "").strip()
        text = str(record.get("text") or "").strip()
        if not item_id or not text:
            raise ValueError("each translation needs item_id and text")
        result[item_id] = record
    return result


def apply_translations(db_path: Path, translations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    updated: list[str] = []
    try:
        with connection:
            for item_id, record in translations.items():
                row = connection.execute(
                    "SELECT language, raw_json FROM information_items WHERE id = ?", (item_id,)
                ).fetchone()
                if row is None:
                    raise ValueError(f"database item not found: {item_id}")
                if str(row["language"] or "").lower() not in {"en", "en-us", "en-gb", "en-zh"}:
                    raise ValueError(f"item is not marked as English: {item_id}")

                raw = json.loads(row["raw_json"] or "{}")
                raw_payload = raw.setdefault("raw_payload", {})
                raw_payload["translation_policy"] = {
                    "required": True,
                    "target_language": "zh-CN",
                    "reviewer": "codex",
                    "preserve_original": True,
                    "status": "complete",
                }
                raw_payload["translation"] = {
                    "source_language": "en",
                    "target_language": "zh-CN",
                    "title": str(record.get("title") or "").strip() or None,
                    "text": str(record["text"]).strip(),
                    "method": "llm_context_translation",
                    "reviewer": "codex",
                    "preserve_tickers": True,
                    "preserve_numbers": True,
                }
                connection.execute(
                    "UPDATE information_items SET raw_json = ? WHERE id = ?",
                    (json.dumps(raw, ensure_ascii=False, sort_keys=True), item_id),
                )
                updated.append(item_id)
    finally:
        connection.close()
    return {"updated": len(updated), "item_ids": updated}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Attach Codex-reviewed Chinese translations without changing the English source text."
    )
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--translations", required=True, type=Path)
    args = parser.parse_args()
    result = apply_translations(args.db, load_translations(args.translations))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
