import hashlib
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'packages/ingestion_scheduler/src'))
from ingestion_scheduler.media import _looks_animated, EXTENSION_BY_MIME
path=root/'runs/discord_repair_20260905/verified_items.jsonl'
items=[json.loads(l) for l in path.read_text().splitlines()]

def retry(item):
    payload=item['raw_payload']; media=payload.setdefault('media',{}).setdefault('static_images',[])
    for a in (payload.get('discord')or{}).get('attachments')or[]:
        mime=a.get('contentType')or''
        if mime not in EXTENSION_BY_MIME or any(x['source_url']==a['url'] for x in media): continue
        with tempfile.TemporaryDirectory() as td:
            tmp=Path(td)/'image'
            download_url=a['url'].replace('cdn.discordapp.com','media.discordapp.net')
            download_url += ('&' if '?' in download_url else '?') + 'width=1600&height=1600&fit=scale-down'
            r=subprocess.run(['curl','-L','--fail','--silent','--max-time','25','-o',str(tmp),'-w','%{content_type}',download_url],capture_output=True,text=True)
            if r.returncode: continue
            actual=r.stdout.strip().split(';')[0]; ext=EXTENSION_BY_MIME.get(actual)
            if not ext: continue
            data=tmp.read_bytes()
            if not data or len(data)>20*1024*1024 or _looks_animated(data,ext): continue
            digest=hashlib.sha256(data).hexdigest(); dest=root/'data/media'/item['source']['id']/item['external']['id']/f'retry-{digest[:12]}{ext}'
            dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(data)
            media.append(dict(kind='static_image',filename=dest.name,mime_type=actual,bytes=len(data),sha256=digest,local_path=str(dest),api_url='/media/'+dest.relative_to(root/'data/media').as_posix(),source_url=a['url']))
    return item
with ThreadPoolExecutor(max_workers=4) as pool: items=list(pool.map(retry,items))
path.write_text(''.join(json.dumps(i,ensure_ascii=False)+'\n' for i in items))
print('static_images',sum(len(i['raw_payload']['media']['static_images']) for i in items))
