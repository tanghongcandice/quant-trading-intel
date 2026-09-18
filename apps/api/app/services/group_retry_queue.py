"""Durable group gaps. Only a committed final-store item closes a retry."""
import hashlib
import json
from datetime import datetime, timezone

SOURCE = 'douyin_group_yuboluo_1'


def key(kind, context):
    return hashlib.sha256(json.dumps([kind, context], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS group_retry_queue(
        fingerprint TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
        evidence_json TEXT NOT NULL, first_run TEXT, last_run TEXT,
        attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, item_id TEXT,
        updated_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS group_retry_attempts(
        id INTEGER PRIMARY KEY, fingerprint TEXT, run_id TEXT, outcome TEXT,
        error TEXT, created_at TEXT NOT NULL)''')


def observe(conn, entries, run_id):
    schema(conn)
    now = datetime.now(timezone.utc).isoformat()
    for entry in entries:
        fp = entry['fingerprint']
        old = conn.execute('SELECT status FROM group_retry_queue WHERE fingerprint=?', (fp,)).fetchone()
        # A complete fresh batch that was never pending needs no queue record.
        if not old and not entry['pending']:
            continue
        conn.execute('''INSERT INTO group_retry_queue
            (fingerprint,kind,status,evidence_json,first_run,last_run,updated_at)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(fingerprint) DO UPDATE SET
            evidence_json=excluded.evidence_json,last_run=excluded.last_run,
            updated_at=excluded.updated_at,
            status=CASE WHEN group_retry_queue.status='resolved' THEN 'resolved' ELSE excluded.status END''',
            (fp, entry['kind'], 'pending' if entry['pending'] else 'awaiting_import',
             json.dumps(entry, ensure_ascii=False), run_id, run_id, now))


def attempt(conn, fingerprint, run_id, error=None):
    schema(conn)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute('INSERT INTO group_retry_attempts(fingerprint,run_id,outcome,error,created_at) VALUES(?,?,?,?,?)',
                 (fingerprint, run_id, 'failed' if error else 'captured', error, now))
    conn.execute('''UPDATE group_retry_queue SET attempts=attempts+1,last_error=?,updated_at=?
                    WHERE fingerprint=? AND status!='resolved' ''', (error, now, fingerprint))


def close_committed(conn, item):
    if (item.get('source') or {}).get('id') != SOURCE:
        return
    schema(conn)
    row = conn.execute('SELECT id,raw_json FROM information_items WHERE source_id=? AND external_id=?',
        (SOURCE, (item.get('external') or {}).get('id'))).fetchone()
    if not row:
        return
    stored = json.loads(row[1])
    parts = (stored.get('raw_payload') or {}).get('message_parts') or []
    supplied = (item.get('raw_payload') or {}).get('message_parts') or []
    # Deduplication alone is insufficient: stored parts must contain the evidence.
    def evidence(rows):
        return [(p.get('voice'),p.get('duration'),p.get('speaker'),p.get('sender_role'),
                 p.get('body'),p.get('shared_video')) for p in rows]
    if not parts or evidence(parts) != evidence(supplied):
        return
    for fp in (item.get('raw_payload') or {}).get('group_retry_keys', []):
        conn.execute("UPDATE group_retry_queue SET status='resolved',item_id=?,last_error=NULL,updated_at=? WHERE fingerprint=?",
            (row[0], datetime.now(timezone.utc).isoformat(), fp))
