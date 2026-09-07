#!/usr/bin/env python3
"""Reuse completed Douyin group voice batches before invoking native ASR.

The page does not expose durable message IDs.  A batch key therefore uses
only verified visible context: resolved time separator, role/avatar identity,
and the ordered voice-duration vector.  DOM indexes and transcript text are
deliberately excluded from the key.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from build_douyin_group import GROUP, SOURCE, TZ, resolve_time


DEFAULT_LEDGER = Path("data/collection_state/douyin_group_voice_ledger.json")


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _avatar(row: dict[str, Any]) -> str:
    for image in row.get("images") or []:
        url = str(image.get("url") or "")
        if "aweme-avatar" in url:
            return url.split("?", 1)[0]
    return str(row.get("author") or "")


def voice_batches(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("group_name") != GROUP:
        raise ValueError("Wrong group")
    captured = datetime.fromisoformat(str(payload["captured_at"]).replace("Z", "+00:00")).astimezone(TZ)
    rows = sorted(payload.get("messages") or [], key=lambda row: int(row["index"]), reverse=True)
    batches: list[dict[str, Any]] = []
    current_time = current_author = current_speaker = current_role = None
    run: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal run
        if not run:
            return
        context = {
            "source_id": SOURCE,
            "created_at": current_time,
            "speaker": current_speaker,
            "role": current_role,
            "durations": [str(row.get("duration") or "") for row in run],
        }
        batches.append(
            {
                "fingerprint": _digest(context),
                "context": context,
                "indexes": [row["index"] for row in run],
                "voices": [str(row.get("voice") or "").strip() for row in run],
            }
        )
        run = []

    for original in rows:
        row = dict(original)
        if row.get("time"):
            next_time = resolve_time(str(row["time"]), captured)
            if next_time != current_time:
                flush()
            current_time = next_time
        text = str(row.get("text") or "")
        if row.get("message_kind") == "system_notice" or (
            not row.get("author") and ("加入了群聊" in text or text.strip() == "我发布了新作品，快来看看！")
        ):
            flush()
            current_author = current_speaker = current_role = None
            continue
        if row.get("author"):
            speaker = _avatar(row)
            if speaker != current_speaker:
                flush()
            current_author = str(row.get("author") or "")
            current_speaker = speaker
            current_role = row.get("role")
        if current_role not in {"群主", "管理员"}:
            flush()
            continue
        if row.get("duration"):
            if not current_time or not current_author:
                flush()
                continue
            run.append(row)
        else:
            flush()
    flush()
    return batches


def _load_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "source_id": SOURCE, "batches": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("batches"), dict):
        raise ValueError("invalid group processing ledger")
    return payload


def _db_item_exists(db_path: Path, item_id: str | None) -> bool:
    if not item_id or not db_path.exists():
        return False
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT 1 FROM information_items WHERE id = ?", (item_id,)).fetchone() is not None


def reuse(payload: dict[str, Any], ledger: dict[str, Any], db_path: Path) -> dict[str, int]:
    rows = {int(row["index"]): row for row in payload.get("messages") or []}
    reused_batches = reused_segments = 0
    for batch in voice_batches(payload):
        stored = (ledger.get("batches") or {}).get(batch["fingerprint"])
        if not stored or not _db_item_exists(db_path, stored.get("item_id")):
            continue
        voices = stored.get("voices") or []
        if len(voices) != len(batch["indexes"]) or not all(str(value).strip() for value in voices):
            continue
        changed = False
        for index, text in zip(batch["indexes"], voices):
            if not str(rows[index].get("voice") or "").strip():
                rows[index]["voice"] = text
                reused_segments += 1
                changed = True
        if changed:
            reused_batches += 1
    return {"reused_batches": reused_batches, "reused_segments": reused_segments}


def record(payload: dict[str, Any], items: list[dict[str, Any]], ledger: dict[str, Any]) -> dict[str, int]:
    item_by_hash = {
        str((item.get("content") or {}).get("hash") or ""): item
        for item in items
        if ((item.get("raw_payload") or {}).get("transcription") or {}).get("audio_count")
    }
    recorded = 0
    now = datetime.now(TZ).isoformat()
    for batch in voice_batches(payload):
        if not batch["voices"] or not all(batch["voices"]):
            continue
        merged = "".join(batch["voices"])
        item = item_by_hash.get(hashlib.sha256(merged.encode()).hexdigest())
        # Paragraph separators affect the built content hash. Fall back to the
        # unique voice item matching this timestamp and audio count.
        if not item:
            matches = [
                candidate for candidate in items
                if (candidate.get("timestamps") or {}).get("created_at") == batch["context"]["created_at"]
                and int((((candidate.get("raw_payload") or {}).get("transcription") or {}).get("audio_count") or 0)) == len(batch["voices"])
            ]
            item = matches[0] if len(matches) == 1 else None
        if not item:
            continue
        ledger.setdefault("batches", {})[batch["fingerprint"]] = {
            "context": batch["context"],
            "voices": batch["voices"],
            "transcript_hash": _digest(batch["voices"]),
            "item_id": item.get("id"),
            "external_id": (item.get("external") or {}).get("id"),
            "completed_at": now,
        }
        recorded += 1
    ledger["updated_at"] = now
    return {"recorded_batches": recorded}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["reuse", "record", "status"])
    parser.add_argument("--snapshot", type=Path, default=Path("data/browser_sessions/douyin_group_yuboluo_1.json"))
    parser.add_argument("--built", type=Path, default=Path("data/douyin_built/yuboluo_group_1.jsonl"))
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--db", type=Path, default=Path("data/quant_intel.sqlite"))
    args = parser.parse_args()
    payload = json.loads(args.snapshot.read_text(encoding="utf-8"))
    ledger = _load_ledger(args.ledger)
    result: dict[str, Any] = {"mode": args.mode, "batches": len(voice_batches(payload))}
    if args.mode == "reuse":
        result.update(reuse(payload, ledger, args.db))
        args.snapshot.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["pending_voice_count"] = sum(not voice for batch in voice_batches(payload) for voice in batch["voices"])
    elif args.mode == "record":
        items = [json.loads(line) for line in args.built.read_text(encoding="utf-8").splitlines() if line.strip()]
        result.update(record(payload, items, ledger))
        args.ledger.parent.mkdir(parents=True, exist_ok=True)
        args.ledger.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        result["ledger_batches"] = len(ledger.get("batches") or {})
        result["reusable_batches"] = sum(
            1 for batch in voice_batches(payload)
            if (ledger.get("batches") or {}).get(batch["fingerprint"])
            and _db_item_exists(args.db, ledger["batches"][batch["fingerprint"]].get("item_id"))
        )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
