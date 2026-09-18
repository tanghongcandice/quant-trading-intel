"""Transactional replacement of incomplete public X posts; never downgrade."""
import json


def update_x_preview(conn, item, run_id):
    if item.get('source', {}).get('type') != 'x':
        return False
    row = conn.execute('SELECT id,raw_json,content_text FROM information_items WHERE source_id=? AND external_id=?',
                       (item['source']['id'], item['external']['id'])).fetchone()
    if not row:
        return False
    old = json.loads(row[1]); prior = old.get('raw_payload') or {}
    if prior.get('subscription_preview') or (prior.get('tweet') or {}).get('subscription_preview'):
        return False
    recovery = (item.get('raw_payload') or {}).get('verified_detail_recovery') or {}
    # A specifically reviewed detail capture can reveal a missing suffix in
    # legacy rows which predate the source_truncated marker.
    verified_extension = (
        recovery.get('method') == 'rendered_detail_text_review'
        and recovery.get('external_id') == item['external']['id']
        and bool(recovery.get('evidence'))
        and ''.join(item['content']['text'].split()).startswith(''.join((row[2] or '').split()))
        and bool(row[2])
    )
    if not (prior.get('source_truncated') or prior.get('tweet', {}).get('source_truncated') or verified_extension):
        return False
    text = item['content']['text']; payload = item.setdefault('raw_payload', {})
    tweet = payload.get('tweet') or {}
    if len(text) <= len(row[2] or ''):
        return False
    if tweet.get('source_truncated') or payload.get('source_truncated') or tweet.get('subscription_preview'):
        raise ValueError('X replacement still incomplete; preserve existing item and retry')
    translation = payload.get('translation')
    if item['content'].get('language') == 'en' and (not translation or translation == prior.get('translation')):
        raise ValueError('X expanded original requires a fresh Chinese translation before replacement')
    item['id'] = row[0]
    payload['source_truncated'] = False
    conn.execute('CREATE TABLE IF NOT EXISTS x_revision_audit(id INTEGER PRIMARY KEY,item_id TEXT,run_id TEXT,old_json TEXT,new_json TEXT)')
    raw = json.dumps(item, ensure_ascii=False)
    conn.execute('INSERT INTO x_revision_audit(item_id,run_id,old_json,new_json) VALUES(?,?,?,?)', (row[0],run_id,row[1],raw))
    conn.execute('UPDATE information_items SET content_text=?,content_hash=?,raw_json=?,collected_at=? WHERE id=?',
                 (text,item['content']['hash'],raw,item['timestamps']['collected_at'],row[0]))
    conn.execute('UPDATE information_items_fts SET content_text=? WHERE item_id=?',(text,row[0]))
    conn.execute('DELETE FROM item_entities WHERE item_id=?',(row[0],))
    return True
