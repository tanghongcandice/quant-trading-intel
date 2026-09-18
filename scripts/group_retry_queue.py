"""Build persistent retry plans from verified visible group message context."""
import argparse
import json
import sqlite3
import sys
import re
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'apps/api'))
from app.services.group_retry_queue import schema, key, observe, attempt
from douyin_group_processing_ledger import voice_batches, _avatar
from build_douyin_group import resolve_time, TZ


def entries(payload):
    result = []
    for batch in voice_batches(payload):
        result.append(dict(batch, kind='voice', fingerprint=key('voice', batch['context']),
                           pending=not all(batch['voices'])))
    current_time = speaker = role = None
    prev = None
    captured = datetime.fromisoformat(payload['captured_at'].replace('Z','+00:00')).astimezone(TZ)
    for row in sorted(payload['messages'], key=lambda r:r['index'], reverse=True):
        if prev is not None and prev-row['index'] != 1:
            current_time = speaker = role = None
        prev = row['index']
        if row.get('message_kind') == 'system_notice' or '加入了群聊' in row.get('text',''):
            speaker = role = None
            continue
        if row.get('time') or row.get('resolved_time'):
            current_time = row.get('resolved_time') or resolve_time(row['time'], captured)
        if row.get('author'):
            speaker, role = _avatar(row), row.get('role')
        if row.get('message_kind') != 'video_share' or role not in {'管理员','群主'} or not current_time:
            continue
        # Actual visible card body/cover plus inherited time and sender, not index.
        text = row.get('text','')
        for prefix in (row.get('time'),row.get('author'),row.get('role')):
            if prefix: text = text.removeprefix(prefix).strip()
        context = {'created_at':current_time, 'speaker':speaker, 'role':role, 'text':text,
                   'images':[i['url'].split('?')[0] for i in row.get('images',[]) if 'aweme-avatar' not in i['url']]}
        result.append({'kind':'card','fingerprint':key('card',context),'context':context,
                       'indexes':[row['index']], 'pending':not bool(row.get('shared_video'))})
    # Identical contexts are ambiguous; do not bind them to one completion.
    counts = {}
    for e in result: counts[e['fingerprint']] = counts.get(e['fingerprint'],0)+1
    for e in result: e['ambiguous'] = counts[e['fingerprint']] > 1
    return result


def sync(root, payload, run_id, items=None):
    descriptors = entries(payload)
    with sqlite3.connect(root/'data/quant_intel.sqlite') as conn:
        observe(conn, descriptors, run_id)
        for item in items or []:
            indexes = [p['index'] for p in item['raw_payload']['message_parts']]
            item['raw_payload']['group_retry_keys'] = [e['fingerprint'] for e in descriptors
                if not e['ambiguous'] and not e['pending'] and e['indexes'] == indexes]
        rows = conn.execute("SELECT fingerprint,kind,status,evidence_json,attempts,last_error,item_id FROM group_retry_queue WHERE status!='resolved'").fetchall()
    plan = [{'fingerprint':r[0],'kind':r[1],'status':r[2],'evidence':json.loads(r[3]),
             'attempts':r[4],'last_error':r[5]} for r in rows]
    return {'pending_count':len(plan),'pending':plan,
            'visible_candidates':descriptors,
            'pending_video_indexes':[e['indexes'][0] for e in descriptors if e['kind']=='card' and e['pending'] and not e['ambiguous']]}


def report(root, run_id):
    with sqlite3.connect(root/'data/quant_intel.sqlite') as conn:
        schema(conn)
        rows = conn.execute('SELECT fingerprint,kind,status,attempts,last_error,item_id FROM group_retry_queue').fetchall()
    data = {'run_id':run_id,'pending_count':sum(r[2]!='resolved' for r in rows),
            'resolved_count':sum(r[2]=='resolved' for r in rows),
            'items':[dict(zip(('fingerprint','kind','status','attempts','last_error','item_id'),r)) for r in rows]}
    folder=root/'runs'/run_id; folder.mkdir(parents=True,exist_ok=True)
    from browser_session_bridge import _write_atomic
    _write_atomic(folder/'group_retry_report.json',data)
    return data


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id',required=True)
    p.add_argument('--attempt-key')
    p.add_argument('--error')
    a=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',a.run_id): p.error('Invalid run ID')
    if a.attempt_key:
        if not re.fullmatch(r'[a-f0-9]{64}',a.attempt_key): p.error('Invalid fingerprint')
        with sqlite3.connect(ROOT/'data/quant_intel.sqlite') as conn:
            attempt(conn,a.attempt_key,a.run_id,a.error)
    print(json.dumps(report(ROOT,a.run_id),ensure_ascii=False))
