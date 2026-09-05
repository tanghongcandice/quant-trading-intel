#!/usr/bin/env python3
"""Convert rendered Douyin profile captures into scheduler-ready JSONL.

The browser bridge deliberately stores only DOM records (``works``).  This
small preparation step is idempotent and runs immediately before collection,
so scheduled jobs no longer depend on a manually invoked builder command.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROFILES = {
    "douyin_jiujiujiucai": {
        "snapshot": "data/browser_sessions/douyin_jiujiujiucai.jsonl",
        "output": "data/douyin_built/jiujiujiucai.jsonl",
        "author_name": "久韭究财",
        "author_external_id": "MS4wLjABAAAAfZSJLO6q-2SWxDS2tp2oor3lawUH4JB2TPKWOGoykXU",
        "profile_url": "https://www.douyin.com/user/MS4wLjABAAAAfZSJLO6q-2SWxDS2tp2oor3lawUH4JB2TPKWOGoykXU",
    },
    "douyin_panyiyoudianshen": {
        "snapshot": "data/browser_sessions/douyin_panyiyoudianshen.jsonl",
        "output": "data/douyin_built/panyiyoudianshen.jsonl",
        "author_name": "潘姨有点神",
        "author_external_id": "",
        "profile_url": "https://www.douyin.com/",
    },
}


def _load(path: Path) -> dict:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {"works": []}
    payload = json.loads(text)
    if isinstance(payload, list):
        return {"works": payload}
    if not isinstance(payload, dict) or not isinstance(payload.get("works"), list):
        raise ValueError(f"invalid Douyin snapshot: {path}")
    return payload


def _cursor_cutoff(root: Path, source_id: str) -> datetime | None:
    db = root / "data" / "quant_intel.sqlite"
    if not db.exists():
        return None
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS source_cursors (
            source_id TEXT PRIMARY KEY, last_successful_created_at TEXT,
            last_successful_external_id TEXT, updated_at TEXT NOT NULL, run_id TEXT NOT NULL
        )""")
        row = conn.execute("SELECT last_successful_created_at FROM source_cursors WHERE source_id = ?", (source_id,)).fetchone()
    if not row or not row[0]:
        return None
    try:
        return datetime.fromisoformat(str(row[0]).replace("Z", "+00:00")) - timedelta(hours=2)
    except ValueError:
        return None


def prepare(root: Path, source_id: str, *, allow_missing: bool = False) -> dict:
    cfg = PROFILES[source_id]
    snapshot_path = root / cfg["snapshot"]
    output_path = root / cfg["output"]
    if not snapshot_path.exists():
        if allow_missing:
            return {"source_id": source_id, "status": "missing"}
        raise FileNotFoundError(snapshot_path)

    payload = _load(snapshot_path)
    # The current standard builder requires media/ASR for full transcription.
    # Browser-only collection has no authorized audio payload, so mark these
    # cards title-only while preserving the normal information_item schema.
    works = []
    snapshot_count = len(payload["works"])
    cutoff = _cursor_cutoff(root, source_id)
    for work in payload["works"]:
        if not work.get("pinned"):
            row = dict(work)
            # ``no_audio`` is a legacy marker from browser-only captures.  It
            # must not suppress the new video-download/ASR recovery pass.
            # Recompute it below from the assets actually found this run.
            if not row.get("review_only"):
                row.pop("no_audio", None)
                row.pop("no_speech", None)
            if cutoff is not None:
                raw = row.get("created_at") or row.get("create_time") or row.get("publish_time")
                if raw is None and str(row.get("aweme_id") or "").isdigit():
                    try:
                        raw = datetime.fromtimestamp(int(row["aweme_id"]) >> 32, tz=timezone.utc).isoformat()
                    except (ValueError, OSError, OverflowError):
                        raw = None
                try:
                    if isinstance(raw, (int, float)):
                        value = datetime.fromtimestamp(raw, tz=timezone.utc)
                    else:
                        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                    if value < cutoff:
                        continue
                except (TypeError, ValueError):
                    pass
            works.append(row)
    normalized = {"author": payload.get("author") or cfg["author_name"], "works": works}
    temp = root / "runs" / f".{source_id}.normalized.json"
    temp.parent.mkdir(parents=True, exist_ok=True)
    temp.write_text(json.dumps(normalized, ensure_ascii=False), encoding="utf-8")
    # Public browser-captured works are enriched from the actual video track.
    # Member-only previews remain title-only and are never downloaded.
    import subprocess, sys, os
    # Keep all ingestion subprocesses on the project environment so optional
    # YAML/NumPy/Whisper dependencies cannot silently disappear.
    project_python = root / ".venv" / "bin" / "python"
    if project_python.exists():
        sys.executable = str(project_python)
    enrich = root / "scripts" / "enrich_douyin_audio.py"
    if enrich.exists():
        subprocess.run([sys.executable, str(enrich), "--snapshot", str(temp),
                        "--metadata-root", str(root / "data" / "douyin_metadata"),
                        "--whisper-dir", str(root / "data" / "whisper"),
                        "--media-dir", str(root / "data" / "douyin_media"),
                        "--author-name", cfg["author_name"]], cwd=str(root),
                       env={**os.environ}, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        transcribe = root / "scripts" / "transcribe_douyin_batch.py"
        subprocess.run([sys.executable, str(transcribe), "--metadata-root",
                        str(root / "data" / "douyin_metadata"), "--output-dir",
                        str(root / "data" / "whisper"), "--prepared-dir",
                        str(root / "data" / "whisper" / "prepared_audio"),
                        "--media-root", str(root / "data" / "douyin_media"),
                        "--author-name", cfg["author_name"]], cwd=str(root),
                       env={**os.environ}, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # Keep the standard builder total: an individual failed download is
    # represented as title-only, while successful video/audio jobs use ASR.
    metadata_ids = {p.stem.replace('_data','') for p in (root / 'data' / 'douyin_metadata').rglob('*_data.json')}
    whisper_ids = {p.stem for p in (root / 'data' / 'whisper').glob('*.json')}
    for row in works:
        if row.get('review_only'):
            continue
        aid = str(row.get('aweme_id'))
        if aid not in metadata_ids or aid not in whisper_ids:
            row['no_audio'] = True
    # Pass the recomputed per-card fallback markers to the builder.  The
    # builder consumes the normalized snapshot file, not the local `works`
    # list, so mutating only the list previously caused false hard failures
    # for cards without Whisper output.
    normalized["works"] = works
    temp.write_text(json.dumps(normalized, ensure_ascii=False), encoding="utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    api = root / "apps" / "api"
    cmd = [sys.executable, "-m", "app.jobs.build_douyin_profile_items",
           "--snapshot", str(temp), "--metadata-root", str(root / "data" / "douyin_metadata"),
           "--whisper-dir", str(root / "data" / "whisper"), "--output", str(output_path),
           "--source-id", source_id, "--author-name", cfg["author_name"],
           "--author-external-id", cfg["author_external_id"], "--profile-url", cfg["profile_url"]]
    result = subprocess.run(cmd, cwd=api, env={**__import__("os").environ, "PYTHONPATH": str(api)},
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    def _work_time(w: dict) -> str:
        raw = w.get('created_at') or w.get('create_time') or w.get('publish_time')
        if raw:
            return str(raw)
        aid = str(w.get('aweme_id') or '')
        if aid.isdigit():
            try:
                return datetime.fromtimestamp(int(aid) >> 32, tz=timezone.utc).isoformat().replace('+00:00', 'Z')
            except (ValueError, OSError, OverflowError):
                pass
        return ''
    snapshot_latest = max((_work_time(w) for w in payload.get("works", [])), default=None)
    # ``cutoff`` intentionally includes a two-hour overlap for collection,
    # so freshness must be compared with the actual cursor (cutoff + overlap),
    # otherwise a snapshot exactly at the cursor would look fresh.
    freshness = "stale_snapshot" if cutoff and (not snapshot_latest or snapshot_latest <= (cutoff + timedelta(hours=2)).isoformat()) else "ready"
    return {"source_id": source_id, "status": freshness, "snapshot_items": snapshot_count,
            "candidate_items": len(works), "cursor_cutoff": cutoff.isoformat() if cutoff else None,
            "snapshot_latest": snapshot_latest,
            "output": str(output_path)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    results = [prepare(args.root.resolve(), source_id, allow_missing=True) for source_id in PROFILES]
    print(json.dumps({"status": "success", "profiles": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
