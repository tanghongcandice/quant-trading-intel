import json
import sqlite3
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with sqlite3.connect(root/'data/quant_intel.sqlite') as db:
    count=0
    for line in (root/'runs/discord_repair_20260905/verified_items.jsonl').read_text().splitlines():
        item=json.loads(line); images=(item['raw_payload'].get('media')or{}).get('static_images')or[]
        if not images:continue
        assert all(Path(i['local_path']).exists() for i in images)
        row=db.execute('SELECT id,raw_json FROM information_items WHERE source_id=? AND external_id=?',(item['source']['id'],item['external']['id'])).fetchone()
        if not row:continue
        iid,text=row; doc=json.loads(text); doc['raw_payload'].setdefault('media',{})['static_images']=images
        db.execute('UPDATE information_items SET raw_json=? WHERE id=?',(json.dumps(doc,ensure_ascii=False),iid));count+=len(images)
    db.commit()
print('images_attached',count)
