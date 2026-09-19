"""Close old retry aliases using a unique text-anchored DOM overlap and final DB.

Never copies transcripts. Both captures are hash-validated; fresh transcripts
must already match committed message_parts. Original queue evidence is retained.
"""
import argparse
import copy
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from group_capture_checkpoint import signature, stamp, validate_capture, digest
from douyin_group_processing_ledger import _avatar

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'douyin_group_yuboluo_1'


def verified_shift(old, fresh, committed_parts):
    previous = {r['index']:r for r in old['messages']}
    current = {r['index']:r for r in fresh['messages']}
    if len(previous)<3 or sorted(previous)!=list(range(min(previous),max(previous)+1)):
        raise ValueError('Contiguous original evidence required')
    # A non-voice body, not a bare clock or repeated duration, anchors alignment.
    anchors = [(i,r) for i,r in previous.items() if not r.get('duration') and signature(r)[0]]
    candidates = {j-i for i,r in anchors for j,s in current.items()
                  if not s.get('duration') and signature(r)==signature(s)}
    valid=[]
    for shift in candidates:
        if not all(i+shift in current for i in previous):
            continue
        matched=True
        for i,r in previous.items():
            s=current[i+shift]
            if signature(r)!=signature(s):
                # Only the oldest initial-hydration header may disappear. Its
                # sender must agree with independently committed fresh context.
                part=committed_parts.get(i+shift)
                if not (i==max(previous) and r.get('duration') and r.get('author')
                        and '前' in r.get('time','') and not s.get('author') and part
                        and part.get('speaker')==_avatar(r)
                        and part.get('sender_role')==r.get('role')):
                    matched=False;break
                boundary=copy.deepcopy(r)
                boundary.update(author='',role='',images=[],time='')
                if signature(boundary)!=signature(s):
                    matched=False;break
            if r.get('voice') and r['voice']!=s.get('voice'):
                matched=False;break
        # A dated text anchor disambiguates identical notices on different days.
        dated_anchor=any(i+shift in current and r.get('resolved_time')
            and current[i+shift].get('resolved_time')
            and abs((stamp(r['resolved_time'])-stamp(current[i+shift]['resolved_time'])).total_seconds())<=180
            for i,r in anchors)
        if matched and dated_anchor:
            valid.append(shift)
    if len(valid)!=1:
        raise ValueError('No unique dated text-anchored overlap; keep original retries')
    return valid[0]


def reconcile(root, source_run, run_id):
    folder=root/'runs'/run_id
    old=json.loads((root/'runs'/source_run/'group_checkpoint.json').read_text())
    fresh=json.loads((folder/'group_capture.json').read_text())
    validate_capture(old,root,source_run,allow_partial=True,historical=True)
    validate_capture(fresh,root,run_id,allow_partial=True)
    items=[json.loads(line) for line in (folder/'group_items.jsonl').read_text().splitlines()]
    resolved=[]
    with sqlite3.connect(root/'data/quant_intel.sqlite') as conn:
        parts={}; owners={}
        for item in items:
            row=conn.execute('SELECT id,raw_json FROM information_items WHERE source_id=? AND external_id=?',
                (SOURCE,item['external']['id'])).fetchone()
            if not row:continue
            stored=json.loads(row[1])['raw_payload'].get('message_parts',[])
            supplied=item['raw_payload']['message_parts']
            fields=('voice','duration','speaker','sender_role','body','shared_video')
            if [tuple(p.get(k) for k in fields) for p in stored] != [tuple(p.get(k) for k in fields) for p in supplied]:
                continue
            for part in supplied:
                if part.get('voice'):
                    if part['index'] in parts:raise ValueError('Ambiguous committed part index')
                    parts[part['index']]=part;owners[part['index']]=row[0]
        shift=verified_shift(old,fresh,parts)
        rows=conn.execute("SELECT fingerprint,evidence_json FROM group_retry_queue WHERE first_run=? AND kind='voice' AND status!='resolved'",(source_run,)).fetchall()
        for fp,raw in rows:
            evidence=json.loads(raw)
            indexes=[i+shift for i in evidence['indexes']]
            selected=[parts.get(i) for i in indexes]
            if not selected or any(p is None for p in selected):continue
            ctx=evidence['context']
            if [p['duration'] for p in selected]!=ctx['durations']:continue
            if any(p['speaker']!=ctx['speaker'] or p['sender_role']!=ctx['role'] for p in selected):continue
            item_ids={owners[i] for i in indexes}
            if len(item_ids)!=1:continue
            item_id=item_ids.pop()
            audit={'fingerprint':fp,'item_id':item_id,'old_evidence':evidence,
                'source_run':source_run,'run_id':run_id,'shift':shift,'committed_indexes':indexes,
                'fresh_capture_sha256':digest(fresh),'old_capture_sha256':digest(old)}
            conn.execute('CREATE TABLE IF NOT EXISTS group_retry_resolution_audit(fingerprint TEXT,run_id TEXT,evidence_json TEXT,created_at TEXT)')
            now=datetime.now(timezone.utc).isoformat()
            conn.execute('INSERT INTO group_retry_resolution_audit VALUES(?,?,?,?)',(fp,run_id,json.dumps(audit,ensure_ascii=False),now))
            conn.execute("UPDATE group_retry_queue SET status='resolved',item_id=?,last_error=NULL,updated_at=? WHERE fingerprint=?",(item_id,now,fp))
            resolved.append(audit)
    (folder/'group_retry_reconciliation.json').write_text(json.dumps(resolved,ensure_ascii=False,indent=2))
    return {'resolved_aliases':len(resolved),'matched_index_shift':shift}


if __name__=='__main__':
    import re
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run',required=True);parser.add_argument('--run-id',required=True)
    args=parser.parse_args()
    if not all(re.fullmatch('[A-Za-z0-9_-]+',v) for v in (args.source_run,args.run_id)):
        parser.error('Invalid run IDs')
    print(json.dumps(reconcile(ROOT,args.source_run,args.run_id)))
