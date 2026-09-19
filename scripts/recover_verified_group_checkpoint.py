"""Recover verified historical checkpoint items without claiming a fresh capture."""
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from group_capture_checkpoint import validate_capture
from build_douyin_group import build
from browser_session_bridge import _write_atomic
from douyin_group_processing_ledger import record, _load_ledger, DEFAULT_LEDGER

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'apps/api'))
from app.services.ingestion_service import import_jsonl
from app.services.group_reconciliation import preserve_identity


def recover(root, source_run, after, corrections=None):
    payload = json.loads((root/'runs'/source_run/'group_checkpoint.json').read_text())
    status = validate_capture(payload, root, source_run, allow_partial=True, historical=True)
    items = [i for i in build(payload, allow_partial=True)
             if datetime.fromisoformat(i['timestamps']['created_at']) > datetime.fromisoformat(after)]
    db = root/'data/quant_intel.sqlite'
    run = 'group_recovery_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = root/'data/backups'/f'{run}.sqlite'
    with sqlite3.connect(db) as c:
        with sqlite3.connect(backup) as dest:
            c.backup(dest)
        for item in items:
            preserve_identity(c, item)
            item['raw_payload']['group_capture_progress'] = {
                'complete': False, 'historical_recovery': True,
                'source_run': source_run, 'errors': status['errors']}
            edits = (corrections or {}).get(item['id'], {})
            if edits:
                import hashlib
                original = item['content']['text']
                for old, new in edits.items():
                    item['content']['text'] = item['content']['text'].replace(old, new)
                item['content']['hash'] = hashlib.sha256(item['content']['text'].encode()).hexdigest()
                item['raw_payload']['term_review'] = {'reviewer': 'codex', 'original_text': original, 'corrections': edits}
    folder = root/'runs'/run
    folder.mkdir()
    path = folder/'reviewed_items.jsonl'
    _write_atomic(path, items)
    result = import_jsonl(db, path, run)
    ledger = _load_ledger(root/DEFAULT_LEDGER)
    result['ledger'] = record(payload, items, ledger)
    _write_atomic(root/DEFAULT_LEDGER, ledger)
    result.update(source_run=source_run, backup=str(backup), pending=status,
                  recovered=[{'id':i['id'],'time':i['timestamps']['created_at'],'title':i['content']['title']} for i in items])
    _write_atomic(folder/'recovery_report.json', result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-run', required=True)
    p.add_argument('--after', required=True)
    p.add_argument('--corrections', type=Path)
    a = p.parse_args()
    print(json.dumps(recover(ROOT, a.source_run, a.after,
        json.loads(a.corrections.read_text()) if a.corrections else None), ensure_ascii=False))
