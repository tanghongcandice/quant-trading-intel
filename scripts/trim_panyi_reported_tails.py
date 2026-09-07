"""Auditable, narrowly scoped cleanup; does not certify ASR completion."""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api'))
from app.jobs.repair_douyin_transcripts import content_hash

ENDINGS = {
    '7681190693185003874': '都是被情绪影响的，跟风。',
    '7681479238360758883': '所以不要上头啊。谢谢大家。',
}

def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = ROOT / 'runs' / ('panyi_tail_cleanup_' + stamp)
    folder.mkdir(parents=True)
    with sqlite3.connect(ROOT / 'data/quant_intel.sqlite') as db:
        db.row_factory = sqlite3.Row
        with sqlite3.connect(folder / 'before.sqlite') as backup:
            db.backup(backup)
        audit = []
        for external_id, ending in ENDINGS.items():
            row = db.execute('SELECT * FROM information_items WHERE source_id=? AND external_id=?', ('douyin_panyiyoudianshen', external_id)).fetchone()
            assert row is not None
            original = row['content_text']
            assert original.count(ending) == 1, 'Ambiguous ending; inspect manually'
            cleaned = original[:original.index(ending) + len(ending)]
            doc = json.loads(row['raw_json'])
            audit.append({'external_id': external_id, 'original_row': dict(row), 'removed_tail': original[len(cleaned):]})
            doc['content']['text'] = cleaned
            digest = content_hash(doc['content'].get('title'), cleaned, doc['content'].get('html'))
            doc['content']['hash'] = digest
            transcription = doc.setdefault('raw_payload', {}).setdefault('transcription', {})
            transcription['tail_cleanup'] = {'at': stamp, 'method': 'explicit_reported_ending', 'backup': str(folder), 'fresh_transcription_still_required': True}
            transcription.setdefault('text_refinement', {})['status'] = 'pending_fresh_transcription'
            db.execute('UPDATE information_items SET content_text=?,content_hash=?,raw_json=? WHERE id=?', (cleaned, digest, json.dumps(doc, ensure_ascii=False), row['id']))
            db.execute('UPDATE information_items_fts SET content_text=? WHERE item_id=?', (cleaned, row['id']))
        (folder / 'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2))
        db.commit()
    print(json.dumps({'updated': len(audit), 'backup': str(folder)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
