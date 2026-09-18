"""Save authorized rendered playback observations for transcript recovery.

Local-only form; no credentials, browser storage or private APIs accepted.
Run the resulting download manifest with --download after DOM collection.
"""
import argparse
import json
import sqlite3
import os
import re
import urllib.request
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=None


def save(doc):
    aid=str(doc['id']); assert aid.isdigit()
    assert doc['page_url']==f'https://www.douyin.com/video/{aid}'
    media=urlparse(doc['src']); assert media.scheme=='https' and media.hostname.endswith('.douyinvod.com')
    with sqlite3.connect(ROOT/'data/quant_intel.sqlite') as db:
        row=db.execute("SELECT source_id,raw_json FROM information_items WHERE source_type='douyin' AND external_id=?",(aid,)).fetchone()
    assert row and row[0] in {'douyin_jiujiujiucai','douyin_panyiyoudianshen'}
    item=json.loads(row[1]); expected=item['author']['profile_url']
    if expected not in doc['authors']: raise ValueError('author_not_verified')
    if doc.get('duration',0)<=0: raise ValueError('duration_not_observed')
    if doc.get('restricted'): raise ValueError('subscription_marker_detected')
    assert not item.get('raw_payload',{}).get('access_label')
    MANIFEST.parent.mkdir(parents=True,exist_ok=True)
    with MANIFEST.open('a') as out: out.write(json.dumps(doc,ensure_ascii=False)+'\n')
    return {'saved':aid,'duration':doc['duration']}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
        self.wfile.write('<form method="post"><label>播放页证据<textarea name="payload"></textarea></label><button>保存播放页证据</button></form>'.encode())
    def do_POST(self):
        try:
            assert int(self.headers.get('Content-Length','0'))<100000
            body=parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())
            result=save(json.loads(body['payload'][0]));code=200
        except Exception as exc:
            result={'error':str(exc) or type(exc).__name__};code=400
        self.send_response(code);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
        import html
        self.wfile.write(('<pre id="result">'+html.escape(json.dumps(result,ensure_ascii=False))+'</pre><form method="post"><label>播放页证据<textarea name="payload"></textarea></label><button>保存播放页证据</button></form>').encode())


def download():
    docs={d['id']:d for d in map(json.loads,MANIFEST.read_text().splitlines())}
    for aid,d in docs.items():
        out=ROOT/'data/douyin_media'/aid/'browser_playback.mp4';out.parent.mkdir(parents=True,exist_ok=True)
        try:
            req=urllib.request.Request(d['src'],headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.douyin.com/'})
            with urllib.request.urlopen(req,timeout=45) as response, out.with_suffix('.part').open('wb') as target:
                while chunk:=response.read(1024*1024):target.write(chunk)
            assert out.with_suffix('.part').stat().st_size>1024
            out.with_suffix('.part').replace(out)
            metadata={'aweme_id':aid,'duration':d['duration']*1000,'desc':d['title'],
                      'capture_method':'authorized_browser_rendered_video','observed_url':d['page_url']}
            metadata_path=ROOT/'data/douyin_metadata'/f'{aid}_data.json'
            if metadata_path.exists():
                backup=MANIFEST.parent/'metadata_before'/metadata_path.name
                backup.parent.mkdir(parents=True,exist_ok=True)
                if not backup.exists():backup.write_bytes(metadata_path.read_bytes())
            metadata_path.write_text(json.dumps(metadata,ensure_ascii=False))
            print(json.dumps({'id':aid,'downloaded_bytes':out.stat().st_size}),flush=True)
        except Exception as exc:
            print(json.dumps({'id':aid,'error':type(exc).__name__}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--download',action='store_true')
    parser.add_argument('--run-id',default=os.environ.get('QUANT_RUN_ID'),required=not os.environ.get('QUANT_RUN_ID'))
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.run_id):parser.error('Invalid run ID')
    MANIFEST=ROOT/'runs'/args.run_id/'browser_playback.jsonl'
    if args.download:download()
    else:HTTPServer(('127.0.0.1',8772),Handler).serve_forever()
