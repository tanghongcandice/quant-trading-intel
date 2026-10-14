"""Final-store-driven retries shared by both public Douyin profiles."""
import json
import os
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api'))
from app.services.douyin_access_policy import excluded
from datetime import datetime, timedelta, timezone

STATUSES = {'no_audio_title_only', 'no_speech_title_only', 'reviewed_truncated', 'pending_retry'}


def remaining_budget(root, source_id, run_id=None):
    run_id = run_id or os.environ.get('QUANT_RUN_ID')
    if not run_id:
        return 3
    with sqlite3.connect(root/'data/quant_intel.sqlite') as db:
        db.execute('''CREATE TABLE IF NOT EXISTS douyin_retry_run_attempts(
            run_id TEXT, source_id TEXT, external_id TEXT,
            PRIMARY KEY(run_id,source_id,external_id))''')
        used = db.execute('SELECT count(*) FROM douyin_retry_run_attempts WHERE run_id=? AND source_id=?',
                          (run_id,source_id)).fetchone()[0]
    return max(0,3-used)


def retry_works(root, source_id, cfg, limit=3, force=False, run_id=None):
    limit = min(limit, remaining_budget(root,source_id,run_id))
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
        if excluded(source_id, doc['external']['id']):
            continue
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


def record_attempt(root, source_id, aid, status, error=None, run_id=None):
    now=datetime.now(timezone.utc)
    run_id = run_id or os.environ.get('QUANT_RUN_ID')
    remaining_budget(root,source_id,run_id)
    with sqlite3.connect(root/'data/quant_intel.sqlite') as db:
        increment = 1
        if run_id:
            increment = db.execute('INSERT OR IGNORE INTO douyin_retry_run_attempts VALUES(?,?,?)',
                                   (run_id,source_id,aid)).rowcount
        db.execute('''INSERT INTO douyin_retry_attempts(source_id,external_id,attempts,last_attempt,next_retry,status,error)
            VALUES(?,?,1,?,?,?,?) ON CONFLICT(source_id,external_id) DO UPDATE SET
            attempts=attempts+?,last_attempt=excluded.last_attempt,next_retry=excluded.next_retry,
            status=excluded.status,error=excluded.error''',
            (source_id,aid,now.isoformat(),(now+timedelta(hours=6)).isoformat(),status,error,increment))
