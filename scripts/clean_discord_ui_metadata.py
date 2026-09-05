"""Repair Discord UI metadata, preserving an SQLite backup and raw exports."""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packages/ingestion_scheduler/src'))
from ingestion_scheduler.adapters.discord import clean_discord_body
from ingestion_scheduler.models import content_hash

if __name__ == '__main__':
    backup = ROOT / 'runs' / ('discord_ui_cleanup_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite')
    with sqlite3.connect(ROOT / 'data/quant_intel.sqlite') as db:
        with sqlite3.connect(backup) as dest:
            db.backup(dest)
        changed = 0
        for iid, old, raw in db.execute("SELECT id,content_text,raw_json FROM information_items WHERE source_type='discord'").fetchall():
            doc = json.loads(raw)
            new = clean_discord_body(old)
            payload = doc.get('raw_payload') or {}
            context = payload.get('reply_context') or {}
            context_old = context.get('content')
            context_new = clean_discord_body(context_old)
            if new == (old or None) and context_old == context_new:
                continue
            doc.setdefault('content', {})['text'] = new
            if context_old != context_new:
                context['content'] = context_new
            # raw_payload.discord remains untouched for provenance.
            digest = content_hash(doc['content'].get('title'), new, doc['content'].get('html'))
            db.execute('UPDATE information_items SET content_text=?,content_hash=?,raw_json=? WHERE id=?', (new, digest, json.dumps(doc, ensure_ascii=False), iid))
            db.execute('UPDATE information_items_fts SET content_text=? WHERE item_id=?', (new or '', iid))
            changed += 1
        db.commit()
        empty = db.execute("SELECT COUNT(*) FROM information_items WHERE source_type='discord' AND LENGTH(TRIM(COALESCE(content_text,'')))=0 AND COALESCE(json_array_length(raw_json,'$.raw_payload.media.static_images'),0)=0 AND COALESCE(json_array_length(raw_json,'$.raw_payload.static_images'),0)=0").fetchone()[0]
    print(json.dumps({'cleaned_records': changed, 'empty_discord_records_hidden': empty, 'backup': str(backup)}, ensure_ascii=False))
