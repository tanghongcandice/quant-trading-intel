"""Final-store-driven retries shared by both public Douyin profiles."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

STATUSES = {'no_audio_title_only', 'no_speech_title_only', 'reviewed_truncated', 'pending_retry'}


def retry_works(root, source_id, cfg, limit=3, force=False):
    if limit <= 0:
        return []
    with sqlite3.connect(root / 'data/quant_intel.sqlite') as db:
        db.execute('''CREATE TABLE IF NOT EXISTS douyin_retry_attempts(
            source_id TEXT, external_id TEXT, attempts INTEGER NOT NULL DEFAULT 0,
            last_attempt TEXT, next_retry TEXT, status TEXT, error TEXT,
            PRIMARY KEY(source_id,external_id))''')
        rows = db.execute('''SELECT i.raw_json, a.attempts, a.next_retry FROM information_items i
            LEFT JOIN douyin_retry_attempts a ON a.source_id=i.source_id AND a.external_id=i.external_id
            WHERE i.source_id=? ORDER BY coalesce(a.last_attempt,''),i.created_at DESC''',(source_id,)).fetchall()
    result=[]; now=datetime.now(timezone.utc).isoformat()
    for raw, attempts, next_retry in rows:
        doc=json.loads(raw); p=doc.get('raw_payload') or {}; t=p.get('transcription') or {}
        if t.get('status') not in STATUSES or p.get('access_label') or p.get('subscription_preview'):
            continue
        ownership=p.get('ownership') or {}
        if not ownership.get('verified') or ownership.get('profile_url') != cfg['profile_url']:
            continue
        if not force and ((attempts or 0)>=5 or (next_retry and next_retry>now)):
            continue
        result.append({'aweme_id':doc['external']['id'],'url':doc['external']['url'],
                       'title':doc['content'].get('title'),'profile_url':cfg['profile_url'],
                       'ownership_verified':True,'retry_transcription':True,
                       'created_at':doc['timestamps']['created_at']})
        if len(result)>=limit:
            break
    return result


def record_attempt(root, source_id, aid, status, error=None):
    now=datetime.now(timezone.utc)
    with sqlite3.connect(root/'data/quant_intel.sqlite') as db:
        db.execute('''INSERT INTO douyin_retry_attempts(source_id,external_id,attempts,last_attempt,next_retry,status,error)
            VALUES(?,?,1,?,?,?,?) ON CONFLICT(source_id,external_id) DO UPDATE SET
            attempts=attempts+1,last_attempt=excluded.last_attempt,next_retry=excluded.next_retry,
            status=excluded.status,error=excluded.error''',
            (source_id,aid,now.isoformat(),(now+timedelta(hours=6)).isoformat(),status,error))
