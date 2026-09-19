"""Bounded playback fallback in the existing authorized public-profile browser.

Observe only rendered page fields and media responses from normal playback.
No cookies, private API responses, background-music assets or subscription media.
"""
import argparse
import json
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright
from douyin_group_collector import lock
from douyin_retry import retry_works, record_attempt
from prepare_douyin_ingestion import PROFILES
import douyin_playback_bridge as bridge

ROOT = Path(__file__).resolve().parents[1]


def media_url(url):
    parsed = urlparse(url)
    return parsed.scheme == 'https' and bool(parsed.hostname) and parsed.hostname.endswith('.douyinvod.com')


def capture(root, run_id, ids):
    folder = root/'runs'/run_id
    folder.mkdir(parents=True, exist_ok=True)
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Explicit unique IDs required')
    allowed = {}
    for source_id, cfg in PROFILES.items():
        for work in retry_works(root, source_id, cfg):
            allowed[work['aweme_id']] = (source_id, cfg)
    if any(aid not in allowed for aid in ids):
        raise ValueError('ID not eligible: completed, restricted, unverified, cooling down or quota exceeded')
    results = []
    bridge.MANIFEST = folder/'browser_playback.jsonl'
    with lock(root/'data/daily_collection.lock'), lock(root/'data/douyin_public_profile.lock'):
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(str(root/'data/browser_profiles/douyin'), headless=True)
            try:
                for aid in ids:
                    source_id, cfg = allowed[aid]
                    page = context.new_page()
                    media = []
                    def observe(response):
                        # Observe only media fetched by the normal player, never API data.
                        if (response.request.resource_type == 'media' and media_url(response.url)
                                and response.status in (200, 206)):
                            ct = response.headers.get('content-type', '')
                            if ct.startswith(('audio/', 'video/')):
                                media.append({'src':response.url, 'content_type':ct})
                    page.on('response', observe)
                    result = {'id':aid,'source_id':source_id}
                    try:
                        page.goto(f'https://www.douyin.com/video/{aid}',wait_until='domcontentloaded',timeout=45000)
                        deadline = time.monotonic()+30
                        while True:
                            observed = page.evaluate('''() => {
                              const v=document.querySelector('video');
                              return {page_url:location.href,title:document.querySelector('h1')?.innerText || '',
                                body:document.body.innerText, duration:v?.duration || 0,
                                current_src:v?.currentSrc || '',
                                sources:[...document.querySelectorAll('video source')].map(s=>s.src),
                                authors:[...document.querySelectorAll('a[href]')].map(a=>({name:a.innerText.trim(),url:a.href}))};
                            }''')
                            if observed['duration'] and observed['title'] and media:
                                break
                            if time.monotonic()>=deadline:
                                raise RuntimeError('No final playback media observed within deadline')
                            page.wait_for_timeout(500)
                        authors=[a['url'] for a in observed['authors'] if a['name']==cfg['author_name']]
                        if cfg['profile_url'] not in authors:
                            raise RuntimeError('Playback author not verified')
                        import re
                        if re.search(r'会员专属|专属会员|会员专享|会员内容|会员可见|订阅专享|付费作品|付费内容|试看|购买本',observed['body']):
                            raise RuntimeError('Restricted playback marker; retain review_only')
                        # Audio responses from the active player take priority; sources
                        # exposed by the video element are the next exact attribution.
                        candidates=sorted(media,key=lambda m: (not m['content_type'].startswith('audio/'),m['src'] not in observed['sources']))
                        chosen=candidates[0]
                        doc={'id':aid,'page_url':observed['page_url'],'title':observed['title'],
                             'authors':authors,'duration':observed['duration'],'restricted':False,
                             'src':chosen['src'],'media_content_type':chosen['content_type'],
                             'observed_at':datetime.now(timezone.utc).isoformat(),
                             'capture_method':'normal_playback_media_response'}
                        bridge.save(doc)
                        extension='.m4a' if chosen['content_type'].startswith('audio/') else '.mp4'
                        out=root/'data/douyin_media'/aid/('browser_playback'+extension)
                        out.parent.mkdir(parents=True,exist_ok=True)
                        request=urllib.request.Request(chosen['src'],headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.douyin.com/'})
                        with urllib.request.urlopen(request,timeout=45) as response:
                            payload=response.read()
                            content_range=response.headers.get('Content-Range','')
                        if len(payload)<1024:
                            raise RuntimeError('Empty or invalid media body')
                        if content_range and (not content_range.startswith('bytes 0-') or int(content_range.split('/')[-1]) != len(payload)):
                            raise RuntimeError('Incomplete media response body')
                        out.write_bytes(payload)
                        metadata=root/'data/douyin_metadata'/f'{aid}_data.json'
                        if metadata.exists():
                            backup=folder/'metadata_before'/metadata.name
                            backup.parent.mkdir(parents=True,exist_ok=True)
                            if not backup.exists(): backup.write_bytes(metadata.read_bytes())
                        metadata.write_text(json.dumps({'aweme_id':aid,'duration':observed['duration']*1000,
                            'desc':observed['title'],'capture_method':'authorized_browser_rendered_video',
                            'observed_url':observed['page_url'],'local_playback_audio':str(out.resolve()) if extension=='.m4a' else None},ensure_ascii=False))
                        record_attempt(root,source_id,aid,'awaiting_review')
                        result.update(status='awaiting_transcription',bytes=len(payload),duration=observed['duration'],media=str(out))
                    except Exception as exc:
                        # Avoid exposing signed media URLs in logs.
                        error=type(exc).__name__+': '+str(exc).split('https://')[0][:240]
                        record_attempt(root,source_id,aid,'pending_retry',error)
                        result.update(status='pending_retry',error=error)
                    finally:
                        page.close()
                    results.append(result)
                    print(json.dumps(result,ensure_ascii=False),flush=True)
            finally:
                context.close()
    (folder/'playback_capture_result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    return results


if __name__=='__main__':
    import re
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--ids',nargs='+',required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.run_id) or not all(x.isdigit() for x in args.ids):
        parser.error('Invalid run ID or video IDs')
    capture(ROOT,args.run_id,args.ids)
