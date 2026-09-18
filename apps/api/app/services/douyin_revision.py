"""Upgrade incomplete public profile transcripts in the import transaction."""
import json

PROFILE_SOURCES = {'douyin_jiujiujiucai', 'douyin_panyiyoudianshen'}
RETRYABLE = {'no_audio_title_only', 'no_speech_title_only', 'reviewed_truncated', 'pending_retry'}


def update_profile_transcript(conn, item, run_id):
    sid = item.get('source', {}).get('id')
    if sid not in PROFILE_SOURCES:
        return False
    row = conn.execute('SELECT id,raw_json,created_at FROM information_items WHERE source_id=? AND external_id=?',
                       (sid, item['external']['id'])).fetchone()
    if not row:
        return False
    old = json.loads(row[1]); prior = old.get('raw_payload') or {}
    if (prior.get('transcription') or {}).get('status') not in RETRYABLE:
        return False
    payload = item.get('raw_payload') or {}; transcription = payload.get('transcription') or {}
    if transcription.get('status') != 'complete':
        return False
    if prior.get('access_label') or prior.get('subscription_preview') or payload.get('access_label') or payload.get('subscription_preview'):
        raise ValueError('Public transcript retry cannot replace restricted content')
    ownership = payload.get('ownership') or {}
    previous_profile = (prior.get('ownership') or {}).get('profile_url') or old.get('author', {}).get('profile_url')
    if not ownership.get('verified') or ownership.get('profile_url') != previous_profile:
        raise ValueError('Transcript update requires matching verified profile ownership')
    review = transcription.get('text_refinement') or {}
    if review.get('status') != 'reviewed' or review.get('reviewer') != 'codex':
        raise ValueError('Transcript update requires completed Codex review')
    if (payload.get('a_share_term_review') or {}).get('status') != 'passed' or not item['content'].get('text', '').strip():
        raise ValueError('Transcript update requires nonempty text and term review')
    item['id'] = row[0]; item['timestamps']['created_at'] = row[2]
    raw = json.dumps(item, ensure_ascii=False)
    conn.execute('CREATE TABLE IF NOT EXISTS douyin_revision_audit(id INTEGER PRIMARY KEY,item_id TEXT,run_id TEXT,old_json TEXT,new_json TEXT)')
    conn.execute('INSERT INTO douyin_revision_audit(item_id,run_id,old_json,new_json) VALUES(?,?,?,?)', (row[0],run_id,row[1],raw))
    conn.execute('UPDATE information_items SET content_text=?,content_hash=?,raw_json=?,collected_at=? WHERE id=?',
                 (item['content']['text'],item['content']['hash'],raw,item['timestamps']['collected_at'],row[0]))
    conn.execute('UPDATE information_items_fts SET content_text=? WHERE item_id=?',(item['content']['text'],row[0]))
    conn.execute('DELETE FROM item_entities WHERE item_id=?',(row[0],))
    conn.execute('DELETE FROM item_analysis WHERE item_id=?',(row[0],))
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='douyin_retry_attempts'").fetchone():
        conn.execute("UPDATE douyin_retry_attempts SET status='complete',error=NULL,next_retry=NULL WHERE source_id=? AND external_id=?",
                     (sid,item['external']['id']))
    return True
