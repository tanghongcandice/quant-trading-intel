"""Seal a genuinely refreshed, reviewed browser capture for one daily run.

This does not operate Chrome. The scheduled agent must execute the browser
workflow in docs/douyin_group_collection.md before invoking this command.
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from build_douyin_group import build
from douyin_group_processing_ledger import DEFAULT_LEDGER, _load_ledger, record
from browser_session_bridge import _write_atomic

def prepare(root, run_id):
    folder = root / 'runs' / run_id
    source = folder / 'group_checkpoint.json'
    payload = json.loads(source.read_text())
    from group_capture_checkpoint import validate_capture
    validate_capture(payload, root, run_id)
    evidence = payload.get('collection_evidence') or {}
    if evidence.get('run_id') != run_id:
        raise ValueError('Group was not refreshed for this run; old snapshots are forbidden')
    if evidence.get('latest_checked') is not True or evidence.get('overlap_covered') is not True:
        raise ValueError('Latest messages and two-hour overlap have not been checked')
    if evidence.get('pending_voice_count') != 0:
        raise ValueError('Group has untranscribed voice messages')
    captured = datetime.fromisoformat(payload['captured_at'].replace('Z', '+00:00'))
    age = (datetime.now(timezone.utc) - captured).total_seconds()
    if not 0 <= age <= 7200:
        raise ValueError('Group capture is stale or future-dated')
    items = build(payload)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api'))
    from app.services.group_reconciliation import preserve_identity
    db = root / 'data/quant_intel.sqlite'
    if db.exists():
        with sqlite3.connect(db) as conn:
            for item in items:
                preserve_identity(conn, item)
    folder = root / 'runs' / run_id
    folder.mkdir(parents=True, exist_ok=True)
    output = root / 'data/douyin_built/yuboluo_group_1.jsonl'
    output.parent.mkdir(parents=True, exist_ok=True)
    # Keep evidence even if a subsequent process replaces the shared snapshot.
    _write_atomic(folder/'group_capture.json', payload)
    (root/'data/browser_sessions').mkdir(parents=True, exist_ok=True)
    _write_atomic(root/'data/browser_sessions/douyin_group_yuboluo_1.json', payload)
    _write_atomic(output, items)
    _write_atomic(folder/'group_items.jsonl', items)
    data = (folder/'group_items.jsonl').read_bytes()
    # Persist completed voice batches independently of a particular run ID.
    # A later run can perform a lightweight latest/overlap scan, restore these
    # reviewed native-ASR segments, and avoid clicking the same voices again.
    ledger = _load_ledger(root / DEFAULT_LEDGER)
    ledger_stats = record(payload, items, ledger)
    ledger_path = root / DEFAULT_LEDGER
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(ledger_path, ledger)
    receipt = {'run_id':run_id, 'captured_at':payload['captured_at'],
        'version':2, 'capture_sha256':hashlib.sha256((folder/'group_capture.json').read_bytes()).hexdigest(),
        'sha256':hashlib.sha256(data).hexdigest(), 'raw_messages':len(payload['messages']),
        'built_items':len(items), 'pending_voice_count':0, 'status':'ready',
        'processing_ledger':ledger_stats}
    _write_atomic(folder/'group_receipt.json', receipt)
    return receipt

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id', required=True)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    a=p.parse_args()
    if not a.run_id.replace('_','').replace('-','').isalnum():
        p.error('Invalid run ID')
    print(json.dumps(prepare(a.root,a.run_id),ensure_ascii=False))
