from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.db import connect


def _load_scheduler(project_root: Path):
    scheduler_src = project_root / "packages" / "ingestion_scheduler" / "src"
    sys.path.insert(0, str(scheduler_src))
    from ingestion_scheduler.adapters.base import AdapterContext
    from ingestion_scheduler.adapters.discord import DiscordAdapter
    from ingestion_scheduler.utils import canonical_json, sha256_text

    return AdapterContext, DiscordAdapter, canonical_json, sha256_text


def _read_payload(snapshot: str) -> dict[str, Any]:
    if snapshot == "-":
        line = sys.stdin.readline()
        if not line:
            raise ValueError("Discord browser snapshot stdin was empty")
        payload = json.loads(line)
    else:
        payload = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"messages": payload}
    if not isinstance(payload, dict):
        raise ValueError("Discord browser snapshot must be an object or a message array")
    return payload


def _existing_external_ids(db_path: Path, source_id: str) -> set[str]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT external_id FROM information_items WHERE source_id = ? AND external_id IS NOT NULL",
            (source_id,),
        ).fetchall()
    return {str(row[0]) for row in rows}


def _cursor_cutoff(db_path: Path, source_id: str) -> datetime | None:
    """Return the successful cursor minus the required two hour overlap."""
    with connect(db_path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS source_cursors (
            source_id TEXT PRIMARY KEY,
            last_successful_created_at TEXT,
            last_successful_external_id TEXT,
            updated_at TEXT NOT NULL,
            run_id TEXT NOT NULL
        )""")
        row = conn.execute("SELECT last_successful_created_at FROM source_cursors WHERE source_id = ?", (source_id,)).fetchone()
    value = row[0] if row else None
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) - timedelta(hours=2)
    except ValueError:
        return None


def _source_config(project_root: Path, source_id: str) -> dict[str, Any]:
    path = project_root / "configs" / "ingestion" / "premarket.template.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    for source in config.get("sources") or []:
        if source.get("id") == source_id and source.get("type") == "discord":
            return source
    raise ValueError(f"Unknown Discord source id: {source_id}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize an authorized Discord browser snapshot into information_item.v1 JSONL."
    )
    parser.add_argument("--snapshot", default="-", help="Snapshot JSON path, or - for stdin")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--raw-output", type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--run-id")
    args = parser.parse_args()

    settings = get_settings(str(args.db) if args.db else None)
    project_root = settings.project_root
    AdapterContext, DiscordAdapter, canonical_json, sha256_text = _load_scheduler(project_root)
    payload = _read_payload(args.snapshot)
    messages = (
        payload.get("messages")
        or payload.get("Messages")
        or payload.get("items")
        or payload.get("Items")
        or []
    )
    if not isinstance(messages, list):
        raise ValueError("Snapshot messages must be a list")

    if args.raw_output:
        args.raw_output.parent.mkdir(parents=True, exist_ok=True)
        args.raw_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    existing = _existing_external_ids(settings.db_path, args.source_id)
    cutoff = _cursor_cutoff(settings.db_path, args.source_id)
    unseen = []
    for row in messages:
        if str((row or {}).get("id") or "") in existing:
            continue
        if cutoff is not None:
            raw_ts = (row or {}).get("timestamp")
            try:
                message_ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            if message_ts < cutoff:
                continue
        unseen.append(row)
    run_id = args.run_id or datetime.now(timezone.utc).strftime("discord_browser_%Y%m%dT%H%M%SZ")
    run_dir = project_root / "runs" / run_id
    source = _source_config(project_root, args.source_id)
    context = AdapterContext(
        base_dir=project_root,
        run_id=run_id,
        run_dir=run_dir,
        raw_dir=run_dir / "raw",
        collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        dry_run=False,
        timeout_seconds=120,
    )
    result = DiscordAdapter().normalize_docs(source, context, unseen, artifact=str(args.raw_output or args.snapshot))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for item in result.items:
            external_id = (item.get("external") or {}).get("id")
            dedupe_key = f"discord:external_id:{external_id}" if external_id else (
                f"discord:source:{args.source_id}:content:{(item.get('content') or {}).get('hash')}"
            )
            item["id"] = "itm_" + sha256_text(dedupe_key)[:24]
            item.setdefault("ingestion", {})["dedupe_key"] = dedupe_key
            handle.write(canonical_json(item) + "\n")

    print(json.dumps({
        "source_id": args.source_id,
        "snapshot_messages": len(messages),
        "existing_skipped": len(messages) - len(unseen),
        "cursor_cutoff": cutoff.isoformat() if cutoff else None,
        "normalized_items": len(result.items),
        "output": str(args.output),
        "raw_output": str(args.raw_output) if args.raw_output else None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
