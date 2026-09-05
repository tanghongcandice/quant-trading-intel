#!/usr/bin/env python3
"""Merge one rendered Discord batch into a durable browser snapshot."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--payload-b64")
    parser.add_argument("--target-author")
    return parser.parse_args()


def timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def messages(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("messages"), list):
        return [row for row in payload["messages"] if isinstance(row, dict)]
    return []


def main() -> None:
    args = parse_args()
    start = timestamp(args.start)
    end = timestamp(args.end)
    if start is None or end is None:
        raise SystemExit("invalid --start or --end timestamp")

    if args.payload_b64:
        payload = base64.b64decode(args.payload_b64).decode("utf-8")
    else:
        payload = sys.stdin.readline()
    if not payload:
        raise SystemExit("missing JSON snapshot")
    incoming = messages(json.loads(payload))
    existing: list[dict] = []
    if args.output.exists():
        existing = messages(json.loads(args.output.read_text(encoding="utf-8")))

    if args.target_author:
        def is_target(row: dict) -> bool:
            author = row.get("author") or {}
            name = author.get("name") or author.get("displayName") or ""
            return args.target_author in str(name)
        incoming = [row for row in incoming if is_target(row)]
        existing = [row for row in existing if is_target(row)]

    merged = {str(row.get("id")): row for row in existing if row.get("id")}
    for row in incoming:
        row_time = timestamp(row.get("timestamp"))
        if row.get("id") and row_time and start <= row_time <= end:
            merged[str(row["id"])] = row

    ordered = sorted(merged.values(), key=lambda row: (row.get("timestamp") or "", str(row.get("id") or "")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"messages": ordered}, ensure_ascii=False, indent=2), encoding="utf-8")
    first = ordered[0].get("timestamp") if ordered else None
    last = ordered[-1].get("timestamp") if ordered else None
    print(json.dumps({"batch": len(incoming), "total": len(ordered), "first": first, "last": last}, ensure_ascii=False))


if __name__ == "__main__":
    main()
