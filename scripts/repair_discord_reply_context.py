import json, sqlite3
from pathlib import Path
root=Path(__file__).resolve().parents[1]
snap=json.loads((root/'data/browser_sessions/discord_haochi_daqu.json').read_text())['messages']
db=sqlite3.connect(root/'data/quant_intel.sqlite')
for m in snap:
    mid=str(m.get('id')); ref=m.get('referencedMessage')
    if not ref: continue
    row=db.execute("select id,raw_json from information_items where source_id='discord_haochi_daqu' and external_id=?",(mid,)).fetchone()
    if not row: continue
    payload=json.loads(row[1]); payload.setdefault('raw_payload',{})['referencedMessage']=ref
    rc=payload.get('raw_payload',{}).get('reference') or m.get('reference')
    if rc: payload['raw_payload']['reference']=rc
    if payload.get('raw_payload',{}).get('reply_context'):
        payload['raw_payload']['reply_context']['content']=ref.get('content')
    db.execute('update information_items set raw_json=? where id=?',(json.dumps(payload,ensure_ascii=False),row[0]))
db.commit(); print('repaired')
