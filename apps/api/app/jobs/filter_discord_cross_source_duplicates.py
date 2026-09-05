from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any


def normalized_message(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "")
    value = re.sub(r"\s+", " ", value).strip().casefold()
    return value


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalized_message(text).encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove Discord messages already stored by another configured source."
    )
    parser.add_argument("--jsonl", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--against-source", required=True, action="append")
    args = parser.parse_args()

    placeholders = ",".join("?" for _ in args.against_source)
    with sqlite3.connect(args.db) as conn:
        rows = conn.execute(
            f"""
            SELECT id, source_id, external_id, content_text, raw_json
            FROM information_items
            WHERE source_id IN ({placeholders}) AND content_text IS NOT NULL
            """,
            args.against_source,
        ).fetchall()

    existing: dict[str, dict[str, Any]] = {}
    existing_texts: list[tuple[str, dict[str, Any]]] = []
    for item_id, source_id, external_id, text, raw_json in rows:
        duplicate_of = {
            "item_id": item_id,
            "source_id": source_id,
            "external_id": external_id,
        }
        candidates = [str(text or "")]
        try:
            raw_payload = json.loads(raw_json or "{}")
            original = ((raw_payload.get("raw_payload") or {}).get("discord") or {}).get("content")
            if original:
                candidates.append(str(original))
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        for candidate in candidates:
            normalized = normalized_message(candidate)
            if normalized:
                existing.setdefault(fingerprint(candidate), duplicate_of)
                existing_texts.append((normalized, duplicate_of))

    kept: list[str] = []
    skipped: list[dict[str, Any]] = []
    seen_in_batch: set[str] = set()
    for line in args.jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        text = str((item.get("content") or {}).get("text") or "")
        normalized = normalized_message(text)
        key = fingerprint(text)
        duplicate = existing.get(key) if normalized else None
        if duplicate is None and normalized:
            # Older translated rows may have the Chinese translation appended to
            # both content_text and raw_payload.discord.content. In that case the
            # unchanged Club 500 original is still an exact prefix terminated by
            # whitespace, so treat it as the same cross-post.
            duplicate = next(
                (
                    duplicate_of
                    for stored_text, duplicate_of in existing_texts
                    if stored_text.startswith(normalized + " ")
                    or normalized.startswith(stored_text + " ")
                ),
                None,
            )
        if duplicate or key in seen_in_batch:
            skipped.append(
                {
                    "source_id": (item.get("source") or {}).get("id"),
                    "external_id": (item.get("external") or {}).get("id"),
                    "duplicate_of": duplicate or {"batch_fingerprint": key},
                }
            )
            continue
        seen_in_batch.add(key)
        kept.append(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps({"skipped": skipped}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"kept": len(kept), "cross_source_duplicates": len(skipped)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
