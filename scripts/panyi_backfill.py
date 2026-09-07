"""Bounded Panyi queue: local-first preparation, explicit Codex review, audited apply.

No bulk network downloader is invoked here. Missing assets are deferred for a
reviewing agent to fetch with video-downloader within the same 20-item budget.
"""
import argparse
import fcntl
import json
import sqlite3
import sys
import time
from panyi_policy import gate, success, failure
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api'))
from app.jobs.build_douyin_profile_items import build_item, load_metadata, content_hash

SID = 'douyin_panyiyoudianshen'
SEC = 'MS4wLjABAAAAiZFYelCAfbPcGXxkCEZEOpJPi-Fo_frPHiaEA45UerKIM-XTAXssDViEHNRu_bH2'
URL = 'https://www.douyin.com/user/' + SEC
SINCE = '2026-04-26T16:00:00Z'  # April 27, inclusive, Asia/Shanghai
STATE = ROOT / 'data/panyi_backfill_state.json'
DB = ROOT / 'data/quant_intel.sqlite'

def is_verified_complete(doc):
    payload = doc.get('raw_payload') or {}
    transcription = payload.get('transcription') or {}
    text = (doc.get('content') or {}).get('text') or ''
    return (transcription.get('status') == 'complete'
            and (transcription.get('text_refinement') or {}).get('status') == 'reviewed'
            and bool(text.strip())
            and not any(marker in text for marker in ('仅保存标题', '无可转录音轨', '未检测到可靠财经口播')))

def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
    temp.replace(path)

def inventory():
    data = json.loads((ROOT / 'data/panyi_verified_inventory.json').read_text())
    assert data['profile_url'] == URL
    ids = set(data['ids'])
    snap = ROOT / 'data/browser_sessions/douyin_panyiyoudianshen.jsonl'
    if snap.exists():
        for w in json.loads(snap.read_text()).get('works', []):
            if w.get('ownership_verified') and w.get('profile_url') == URL:
                ids.add(str(w['aweme_id']))
    return ids

def backup(db, folder):
    folder.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(folder / 'before.sqlite') as target:
        db.backup(target)

def cleanup():
    ids = inventory()
    folder = ROOT / 'runs' / ('panyi_cleanup_' + str(time.time_ns()))
    with sqlite3.connect(DB) as db:
        backup(db, folder)
        removed = []
        for iid, aid, raw in db.execute('SELECT id,external_id,raw_json FROM information_items WHERE source_id=?', (SID,)).fetchall():
            if aid in ids:
                continue
            doc = json.loads(raw)
            path = Path(doc.get('raw_payload', {}).get('metadata_path') or ROOT / f'data/douyin_metadata/{aid}_data.json')
            detail = json.loads(path.read_text()) if path.exists() else {}
            author = detail.get('author') or {}
            name = (author.get('nickname') if isinstance(author, dict) else author) or detail.get('author_name')
            if not name or name == '潘姨有点神':
                continue  # Absence from a partial profile is not proof.
            removed.append({'id': iid, 'external_id': aid, 'actual_author': name, 'before': doc})
            db.execute('DELETE FROM information_items_fts WHERE item_id=?', (iid,))
            db.execute('DELETE FROM item_entities WHERE item_id=?', (iid,))
            db.execute('DELETE FROM information_items WHERE id=? AND source_id=?', (iid, SID))
        write(folder / 'removed.json', removed)
        db.commit()
    print(json.dumps({'removed':len(removed),'backup':str(folder)},ensure_ascii=False))

def select_next(candidates, state):
    # A selection is not a success: retry it until verified and committed.
    current = state.get('current_id') or state.get('last_selected_id')
    if current in candidates:
        return [current]
    return candidates[:1]

def prepare(state):
    decision = gate(state, time.time())
    if decision:
        print(json.dumps(decision));return
    if state.get('pending_batch'):
        print(json.dumps({'status':'awaiting_review','batch':state['pending_batch']}));return
    ids = inventory()
    with sqlite3.connect(DB) as db:
        docs = {aid: json.loads(raw) for aid,raw in db.execute('SELECT external_id,raw_json FROM information_items WHERE source_id=?',(SID,))}
    candidates = []
    for aid in sorted(ids, reverse=True):
        created = datetime.fromtimestamp(int(aid)>>32, timezone.utc).isoformat().replace('+00:00','Z')
        if created < SINCE: continue
        doc = docs.get(aid, {})
        status = doc.get('raw_payload', {}).get('transcription', {}).get('status')
        if status == 'member_title_only' and doc.get('raw_payload', {}).get('access_label'): continue
        if is_verified_complete(doc): continue
        candidates.append(aid)
    selected = select_next(candidates, state)
    if not selected:
        state['completed'] = True
        write(STATE, state)
        print(json.dumps({'status':'complete','remaining':0}));return
    folder = ROOT / 'runs' / ('panyi_batch_' + str(time.time_ns()))
    folder.mkdir(parents=True)
    deadline = state.get('platform_wait_until',0) if state.get('local_interval_disabled') else time.time()+max(600,state.get('interval_seconds',600))
    state.update(pending_batch=str(folder), next_allowed_at=deadline, selected_ids=selected, last_selected_id=selected[0], current_id=selected[0])
    state.setdefault('selection_history', []).append({'id':selected[0], 'batch':str(folder), 'selected_at':time.time()})
    write(STATE, state)  # Reserve the budget before any work, survives interruption.
    fresh = state.get('force_fresh', False)
    metadata_root = folder / 'metadata' if fresh else ROOT / 'data/douyin_metadata'
    whisper_root = folder / 'whisper' if fresh else ROOT / 'data/whisper'
    metadata_root.mkdir(parents=True, exist_ok=True)
    whisper_root.mkdir(parents=True, exist_ok=True)
    metadata = load_metadata(metadata_root)
    built=[];deferred=[]
    for aid in selected:
        old = docs.get(aid,{})
        work = {'aweme_id':aid,'title':old.get('content',{}).get('title') or '', 'ownership_verified':True,'profile_url':URL}
        try:
            item=build_item(work,metadata,whisper_root,datetime.now(timezone.utc).isoformat(),source_id=SID,author_name='潘姨有点神',author_external_id=SEC,profile_url=URL)
            item['raw_payload']['transcription']['text_refinement']={'status':'pending_codex_review'}
            built.append(item)
        except Exception as exc:
            deferred.append({'id':aid,'reason':str(exc)})
    write(folder/'draft.json',built)
    write(folder/'manifest.json',{'selected_ids':selected,'deferred':deferred,'remaining':len(candidates),'profile_url':URL,'since':SINCE,'force_fresh':fresh,'created_epoch':time.time(),'metadata_root':str(metadata_root),'whisper_root':str(whisper_root)})
    print(json.dumps({'status':'awaiting_review','batch':str(folder),'draft_items':len(built),'deferred':deferred,'remaining':len(candidates)},ensure_ascii=False))

def apply(state, path):
    folder=Path(state['pending_batch'])
    assert path.resolve().parent == folder.resolve()
    reviewed=json.loads(path.read_text())
    assert len(reviewed)==1
    assert is_verified_complete(reviewed[0]), 'Only a complete reviewed transcript advances the queue'
    assert len({d['external']['id'] for d in reviewed})==len(reviewed)
    with sqlite3.connect(DB) as db:
        backup(db, folder)
        for item in reviewed:
            aid=item['external']['id']
            assert aid in state['selected_ids'] and aid in inventory()
            assert item['source']['id']==SID and item['timestamps']['created_at']>=SINCE
            ownership=item['raw_payload']['ownership']
            assert ownership['verified'] and ownership['profile_url']==URL
            assert item['raw_payload']['transcription']['text_refinement'].get('status')=='reviewed'
            if state.get('force_fresh'):
                manifest = json.loads((folder/'manifest.json').read_text())
                assert manifest.get('force_fresh'), 'Legacy batch cannot satisfy fresh capture'
                for key in ('metadata_path', 'audio_path'):
                    resource = Path(item['raw_payload'].get(key) or '').resolve()
                    assert resource.is_relative_to(folder.resolve()) and resource.is_file(), 'Fresh batch asset required: ' + key
                    assert resource.stat().st_mtime >= manifest['created_epoch'], 'Asset predates batch'
                asr = folder/'whisper'/f'{aid}.json'
                assert asr.exists() and asr.stat().st_mtime >= manifest['created_epoch'], 'Fresh ASR required'
            item['content']['hash']=content_hash(item['content'].get('title'),item['content']['text'])
            row=db.execute('SELECT id FROM information_items WHERE source_id=? AND external_id=?',(SID,aid)).fetchone()
            if not row:
                raise ValueError('New IDs must use standard import_jsonl after review, then retry apply')
            iid=row[0];item['id']=iid
            db.execute('UPDATE information_items SET content_text=?,content_hash=?,raw_json=? WHERE id=?',(item['content']['text'],item['content']['hash'],json.dumps(item,ensure_ascii=False),iid))
            db.execute('UPDATE information_items_fts SET content_text=? WHERE item_id=?',(item['content']['text'],iid))
        db.commit()
    state.pop('pending_batch',None)
    state['last_applied_ids']=[d['external']['id'] for d in reviewed]
    state['last_successful_id']=reviewed[0]['external']['id']
    state.pop('current_id', None)
    if state.get('policy_version') == 2:
        success(state)
    write(STATE,state)
    print(json.dumps({'updated':len(reviewed),'backup':str(folder/'before.sqlite')},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['cleanup','prepare','apply','backoff']);p.add_argument('--reviewed',type=Path)
    p.add_argument('--reason',choices=['http_403','http_429','login_required','captcha','ownership_mismatch','download_error','transcription_error','review_failed'],default='download_error')
    p.add_argument('--retry-after-seconds',type=float,default=0)
    args=p.parse_args()
    with (ROOT/'data/panyi_backfill.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=json.loads(STATE.read_text()) if STATE.exists() else {'batch_size':20,'interval_seconds':3600}
        if args.action=='cleanup':cleanup()
        elif args.action=='prepare':prepare(state)
        elif args.action=='apply':apply(state,args.reviewed)
        else:
            if state.get('pending_batch'):
                state.setdefault('failed_batches', []).append({'batch':state.pop('pending_batch'), 'ids':state.get('selected_ids',[]), 'reason':args.reason, 'at':time.time()})
            if state.get('policy_version') == 2:
                failure(state,args.reason,time.time(),args.retry_after_seconds)
            elif state.get('automatic_backoff', True):
                state.update(batch_size=max(1,state.get('batch_size',20)//2),interval_seconds=min(86400,state.get('interval_seconds',3600)*2),next_allowed_at=max(state.get('next_allowed_at',0),time.time()+min(86400,state.get('interval_seconds',3600)*2)))
            else:
                state.update(batch_size=1)
            write(STATE,state);print(json.dumps({'status':'failure_recorded','current_id':state.get('current_id'),'reason':args.reason,'next_allowed_at':state.get('next_allowed_at'),'blocked_reason':state.get('blocked_reason')}))
