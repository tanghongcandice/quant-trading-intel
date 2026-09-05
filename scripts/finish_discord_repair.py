"""Apply the reviewed 2026-09-05 backfill with a recoverable audit."""
import json
import re
import sqlite3
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'apps/api'))
from app.services.ingestion_service import import_jsonl

folder=root/'runs/discord_repair_20260905'
db=root/'data/quant_intel.sqlite'
items=[json.loads(line) for line in (folder/'verified_items.jsonl').read_text().splitlines() if line.strip()]
for item in items:
    text=item['content'].get('text')or''
    if len(re.findall('[A-Za-z]',text))>=4 and not re.search('[\u4e00-\u9fff]',text):
        assert (item.get('raw_payload',{}).get('translation')or{}).get('text'), item['external']
with sqlite3.connect(db) as conn, sqlite3.connect(folder/'before_repair.sqlite') as backup:
    conn.backup(backup)
stats=import_jsonl(db,folder/'verified_items.jsonl',run_id='discord_verified_repair_20260905',mode='verified_backfill')
audit=[]
targets={i['external']['id'] for i in items if i['raw_payload'].get('analysis_role')!='reply_context_only'}
with sqlite3.connect(db) as conn:
    # Preserve captured non-target messages as context-only evidence.
    rows=conn.execute("SELECT id,external_id,raw_json FROM information_items WHERE source_id='discord_haochi_daqu' AND run_id='premarket_20260905T080209Z'").fetchall()
    for iid,eid,raw in rows:
        if eid in targets:
            continue
        old=json.loads(raw)
        if (old.get('author')or{}).get('display_name')=='好吃好吃爱喝奶茶奶茶～～～':
            continue
        audit.append({'id':iid,'before':old,'reason':'reply_avatar_author_misattribution'})
        payload=old.setdefault('raw_payload',{})
        payload.update(analysis_role='reply_context_only',analysis_policy={'include':False,'mode':'context_only'},author_verification='non_target_preserved_for_context')
        conn.execute('UPDATE information_items SET raw_json=? WHERE id=?',(json.dumps(old,ensure_ascii=False),iid))
    for item in items:
        row=conn.execute('SELECT id,raw_json FROM information_items WHERE source_id=? AND external_id=?',(item['source']['id'],item['external']['id'])).fetchone()
        if not row: continue
        iid,raw=row; old=json.loads(raw); payload=item['raw_payload']; prior=old.get('raw_payload')or{}
        for key in ('translation','translation_policy','summary'):
            if key not in payload and prior.get(key): payload[key]=prior[key]
        if not (payload.get('media')or{}).get('static_images') and prior.get('media'): payload['media']=prior['media']
        item['id']=iid
        audit.append({'id':iid,'before':old,'reason':'verified_author_body_and_context'})
        conn.execute('UPDATE information_items SET raw_json=?,content_text=?,content_hash=?,author_handle=?,author_display_name=? WHERE id=?',
            (json.dumps(item,ensure_ascii=False),item['content'].get('text'),item['content'].get('hash'),item['author'].get('handle'),item['author'].get('display_name'),iid))
        conn.execute('UPDATE information_items_fts SET content_text=? WHERE item_id=?',(item['content'].get('text'),iid))
    conn.commit()
(folder/'repair_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
stats['corrected_non_target']=sum(a['reason']=='reply_avatar_author_misattribution' for a in audit)
stats['verified_targets']=len(targets)
(folder/'repair_result.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2))
print(json.dumps(stats,ensure_ascii=False))
