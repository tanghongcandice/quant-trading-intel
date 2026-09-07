"""Backfill explicit preview evidence; preserve a SQLite backup before changing rows."""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api'))
from app.services.subscription_policy import enforce_subscription_policy

def main():
    conn = sqlite3.connect(ROOT / 'data/quant_intel.sqlite')
    backup = ROOT / 'runs' / ('subscription-backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.sqlite')
    with sqlite3.connect(backup) as dest:
        conn.backup(dest)
    changed = []
    with conn:
        for ident, raw_json in conn.execute("SELECT id,raw_json FROM information_items WHERE source_type IN ('x','douyin')").fetchall():
            item = json.loads(raw_json)
            if (item.get('source') or {}).get('id') == 'x_aleabitoreddit' and str((item.get('external') or {}).get('id')) == '2096780048187773122':
                item.setdefault('raw_payload', {}).update(subscription_preview=True, subscription_evidence='User confirmed subscription preview on 2026-09-07')
            enforce_subscription_policy(item)
            if item != json.loads(raw_json):
                conn.execute('UPDATE information_items SET raw_json=? WHERE id=?', (json.dumps(item, ensure_ascii=False), ident))
                changed.append(ident)
    print(json.dumps({'updated': changed, 'backup': str(backup)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
