import json
import sqlite3
from pathlib import Path
root=Path(__file__).resolve().parents[1]
folder=root/'runs/discord_repair_20260905'
raw={m['id']:m for m in json.loads((folder/'verified_raw.json').read_text())['messages']}
items=[json.loads(l) for l in (folder/'verified_items.jsonl').read_text().splitlines()]
filled=0; pending=[]
with sqlite3.connect(root/'data/quant_intel.sqlite') as db:
    for item in items:
        row=db.execute('SELECT id,raw_json FROM information_items WHERE source_id=? AND external_id=?',(item['source']['id'],item['external']['id'])).fetchone()
        if not row:continue
        iid,text=row; doc=json.loads(text); payload=doc['raw_payload']; reply=payload.get('reply_context')or{}
        parent=raw.get(reply.get('id'))or{}
        author=parent.get('author')or{}
        if author.get('name') and author['name']!='Unknown Discord author':
            reply['author']={'display_name':author['name'],'handle':author['name'],'external_id':author.get('id')}; filled+=1
        media=payload.get('media')or{}; saved={a['source_url'] for a in media.get('static_images')or[]}
        for a in (payload.get('discord')or{}).get('attachments')or[]:
            if a.get('contentType') in ('image/jpeg','image/png','image/webp','image/avif') and a['url'] not in saved:
                pending.append({'external_id':doc['external']['id'],'filename':a['fileName'],'url':a['url'],'reason':'download_timeout_or_unavailable'})
        db.execute('UPDATE information_items SET raw_json=? WHERE id=?',(json.dumps(doc,ensure_ascii=False),iid))
    db.commit()
(folder/'pending_images.json').write_text(json.dumps(pending,ensure_ascii=False,indent=2))
print(json.dumps({'reply_authors_filled':filled,'pending_images':len(pending)}))
