"""Reconcile verified growing native-ASR batches against the final store."""
import copy
import json
from datetime import datetime

SOURCE = 'douyin_group_yuboluo_1'


def match_existing(conn, item):
    if (item.get('source') or {}).get('id') != SOURCE: return None
    raw = item.get('raw_payload') or {}
    parts = raw.get('message_parts') or []
    if not raw.get('transcription', {}).get('audio_count') or not parts: return None
    matches = []
    for row in conn.execute('SELECT id,external_id,raw_json,content_hash,created_at FROM information_items WHERE source_id=?', (SOURCE,)):
        old = json.loads(row[2])
        previous = (old.get('raw_payload') or {}).get('message_parts') or []
        if not previous: continue
        if not all(p.get('voice') for p in previous + parts): continue
        if len(previous) < len(parts) and len(previous) < 2: continue
        if previous[0].get('speaker') != parts[0].get('speaker'): continue
        if previous[0].get('sender_role') != parts[0].get('sender_role'): continue
        a = datetime.fromisoformat(row[4].replace('Z', '+00:00'))
        b = datetime.fromisoformat(item['timestamps']['created_at'].replace('Z', '+00:00'))
        if a.date() != b.date() or abs((a-b).total_seconds()) > 180: continue
        if len(previous) > len(parts):
            if len(parts) >= 2 and [(p.get('duration'),p['voice']) for p in previous[:len(parts)]] == [(p.get('duration'),p['voice']) for p in parts]:
                raise ValueError('Group batch is a shorter stored prefix; recheck capture instead of duplicating it')
            continue
        if [(p.get('duration'),p['voice']) for p in previous] != [(p.get('duration'),p['voice']) for p in parts[:len(previous)]]: continue
        matches.append({'id':row[0], 'external_id':row[1], 'item':old,
                        'content_hash':row[3], 'created_at':row[4]})
    if len(matches) > 1:
        raise ValueError('Ambiguous group batch identity; explicit reconciliation required')
    return matches[0] if matches else None


def preserve_identity(conn, item):
    previous = match_existing(conn, item)
    if previous:
        item['id'] = previous['id']
        item['external']['id'] = previous['external_id']
        item.setdefault('ingestion', {})['dedupe_key'] = SOURCE + ':' + previous['external_id']
        old_content = previous['item'].get('content') or {}
        # Keep reviewed paragraph boundaries of an unchanged batch.
        if (item['content']['text'].replace('\n','') == (old_content.get('text') or '').replace('\n','')):
            item['content']['text'] = old_content['text']
            item['content']['hash'] = old_content['hash']
    return previous


def update_existing(conn, item, run_id):
    previous = preserve_identity(conn, item)
    if not previous: return False
    if previous['content_hash'] == item['content']['hash'] and previous['created_at'] == item['timestamps']['created_at']:
        return False
    # Both row backup and update live in the caller's import transaction.
    conn.execute('''CREATE TABLE IF NOT EXISTS group_revision_audit(
        id INTEGER PRIMARY KEY, item_id TEXT NOT NULL, run_id TEXT NOT NULL,
        old_json TEXT NOT NULL, new_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    original_row = conn.execute('SELECT * FROM information_items WHERE id=?', (previous['id'],)).fetchone()
    new = copy.deepcopy(item)
    new.setdefault('raw_payload', {})['revision'] = {'run_id':run_id,
        'previous_audio_count':previous['item']['raw_payload']['transcription']['audio_count'],
        'reason':'verified_native_asr_prefix_extension_or_explicit_time'}
    conn.execute('INSERT INTO group_revision_audit(item_id,run_id,old_json,new_json) VALUES(?,?,?,?)',
        (previous['id'],run_id,json.dumps(dict(original_row),ensure_ascii=False),json.dumps(new,ensure_ascii=False)))
    conn.execute('''UPDATE information_items SET title=?,content_text=?,content_hash=?,
        created_at=?,collected_at=?,raw_json=? WHERE id=?''',
        (new['content']['title'],new['content']['text'],new['content']['hash'],new['timestamps']['created_at'],
         new['timestamps']['collected_at'],json.dumps(new,ensure_ascii=False),previous['id']))
    conn.execute('UPDATE information_items_fts SET title=?,content_text=? WHERE item_id=?',
        (new['content']['title'],new['content']['text'],previous['id']))
    item.update(new)
    return True
