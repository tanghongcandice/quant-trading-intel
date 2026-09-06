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

    # Use the same evidence rules as final ingestion. No within-source text
    # suppression: distinct Discord IDs can legitimately contain the same text.
    from app.services.discord_guard import duplicate, sid, TIANYI
    with sqlite3.connect(args.db) as db:
        stored = [json.loads(r[0]) for r in db.execute('SELECT raw_json FROM information_items WHERE source_type=?', ('discord',))]
    candidates = [json.loads(line) for line in args.jsonl.read_text().splitlines() if line.strip()]
    candidates.sort(key=lambda item: sid(item) != TIANYI)
    accepted, audit = [], []
    for item in candidates:
        match = next((other for other in stored + accepted if sid(other) in args.against_source and duplicate(item, other)), None)
        if match and sid(item) != TIANYI:
            audit.append({'source_id':sid(item),'external_id':item.get('external',{}).get('id'),'duplicate_of':{'item_id':match.get('id'),'source_id':sid(match)}})
        else:
            accepted.append(item)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(''.join(json.dumps(i,ensure_ascii=False)+'\n' for i in accepted))
    args.audit.write_text(json.dumps({'skipped':audit},ensure_ascii=False,indent=2))
    print(json.dumps({'kept':len(accepted),'cross_source_duplicates':len(audit)}))
    return


if __name__ == "__main__":
    main()
