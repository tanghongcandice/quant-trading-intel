"""Bounded playback fallback in the existing authorized public-profile browser.

Observe only rendered page fields and media responses from normal playback.
No cookies, private API responses, background-music assets or subscription media.
"""
import argparse
import json
import re
import hashlib
import subprocess
import time
import base64
import os
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright
from douyin_group_collector import lock
from douyin_retry import retry_works, record_attempt, remaining_budget
from prepare_douyin_ingestion import PROFILES
from app.services.douyin_access_policy import excluded

ROOT = Path(__file__).resolve().parents[1]

# Trace only bytes appended to the visible player's MediaSource. This avoids
# guessing from CDN paths, quality variants or preloaded neighbouring videos.
TRACE_PLAYBACK = r"""(() => {
  const buffers = new WeakMap(), blobs = new Map(), tracks = new WeakMap();
  const originalFetch = window.fetch;
  const wrap = response => {
    // Streaming players concatenate reader chunks before appendBuffer.
    const body = response.body;
    if (body) {
      const getReader = body.getReader.bind(body);
      body.getReader = (...args) => {
        const reader = getReader(...args), readChunk = reader.read.bind(reader);
        reader.read = async (...params) => {
          const chunk = await readChunk(...params);
          if (chunk.value) buffers.set(chunk.value.buffer,response.url);
          return chunk;
        };
        return reader;
      };
    }
    const read = response.arrayBuffer.bind(response);
    response.arrayBuffer = async () => { const b = await read(); buffers.set(b, response.url); return b; };
    const clone = response.clone.bind(response);
    response.clone = () => wrap(clone());
    return response;
  };
  window.fetch = async (...args) => wrap(await originalFetch(...args));
  const open = XMLHttpRequest.prototype.open, send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(...args) { this.__mediaURL = args[1]; return open.apply(this,args); };
  XMLHttpRequest.prototype.send = function(...args) {
    this.addEventListener('load', () => {
      if (this.response instanceof ArrayBuffer) buffers.set(this.response,this.responseURL || this.__mediaURL);
    }); return send.apply(this,args);
  };
  const set = Uint8Array.prototype.set;
  Uint8Array.prototype.set = function(source,...args) {
    const url = buffers.get(source) || buffers.get(source?.buffer);
    const result = set.call(this,source,...args);
    if (url) buffers.set(this.buffer,url);
    return result;
  };
  const slice = ArrayBuffer.prototype.slice;
  ArrayBuffer.prototype.slice = function(...args) {
    const result = slice.apply(this,args), url = buffers.get(this);
    if (url) buffers.set(result,url);
    return result;
  };
  const create = URL.createObjectURL.bind(URL);
  URL.createObjectURL = object => {
    const url = create(object);
    if (object instanceof MediaSource) { const state = {urls:new Set(), types:new Map()}; blobs.set(url,state); tracks.set(object,state); }
    return url;
  };
  const add = MediaSource.prototype.addSourceBuffer;
  MediaSource.prototype.addSourceBuffer = function(type) {
    const sb = add.call(this,type), state = tracks.get(this);
    const append = sb.appendBuffer.bind(sb);
    sb.appendBuffer = bytes => {
      const url = buffers.get(bytes) || buffers.get(bytes.buffer);
      if (state && url) { state.urls.add(url); state.types.set(url,type); }
      return append(bytes);
    }; return sb;
  };
  window.__douyinPlaybackTrace = url => {
    const state = blobs.get(url);
    return state ? [...state.urls].map(src => ({src, type:state.types.get(src)})) : [];
  };
})();"""

DOWNLOAD_MEDIA = r"""async url => {
  const response = await fetch(url, {signal:AbortSignal.timeout(45000)});
  if (![200,206].includes(response.status)) throw new Error('media_http_' + response.status);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.length > 256*1024*1024) throw new Error('media_too_large');
  let binary = '';
  for (let i=0;i<bytes.length;i+=32768) binary += String.fromCharCode(...bytes.subarray(i,i+32768));
  return {body:btoa(binary), range:response.headers.get('Content-Range') || ''};
}"""

READ_PLAYBACK = r'''() => {
  const visible = e => e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
  const videos = [...document.querySelectorAll('video')].filter(visible);
  const v = videos.find(v => !v.paused && v.duration > 0) || videos[0];
  const selectors = ['h1', '[data-e2e="video-desc"]', '[data-e2e="video-title"]',
    '[data-e2e="detail-video-info"] [class*="desc"]'];
  const titles = selectors.flatMap(selector => [...document.querySelectorAll(selector)]
    .filter(visible).map(e => ({selector, text:e.innerText.trim()}))).filter(x => x.text);
  return {page_url:location.href, title:titles[0]?.text || '', title_selector:titles[0]?.selector || null,
    body:document.body.innerText, duration:Number.isFinite(v?.duration) ? v.duration : 0,
    video_count:videos.length, paused:v?.paused, ready_state:v?.readyState,
    current_time:v?.currentTime || 0, video_error:v?.error?.code || null,
    appended_sources:window.__douyinPlaybackTrace?.(v?.currentSrc) || [],
    current_src:v?.currentSrc || '', sources:v ? [...v.querySelectorAll('source')].map(s=>s.src) : [],
    authors:[...document.querySelectorAll('a[href]')].filter(visible).map(a=>({name:a.innerText.trim(),url:a.href}))};
}'''


def missing_playback_reason(observed, media):
    body = observed.get('body', '')
    if re.search(r'会员专属|专属会员|会员专享|会员内容|会员可见|订阅专享|付费作品|付费内容|试看|购买本', body):
        return 'restricted_playback'
    if re.search(r'验证码|完成验证|安全验证|拖动滑块', body):
        return 'verification_required'
    if re.search(r'登录后观看|请登录后|登录已失效', body):
        return 'login_required'
    if not observed.get('video_count'):
        return 'video_element_missing'
    if observed.get('video_error'):
        return 'player_error'
    if not observed.get('title'):
        return 'rendered_title_missing'
    if not observed.get('duration'):
        return 'duration_missing'
    if not media:
        return 'media_response_missing'
    return None


def safe_diagnostics(observed, responses, cfg):
    # Keep public DOM/player facts, never signed URLs, headers or credentials.
    return {k:observed.get(k) for k in ('title', 'title_selector', 'video_count',
        'duration', 'paused', 'ready_state', 'current_time', 'video_error')} | {
        'page_path':urlparse(observed.get('page_url', '')).path,
        'author_verified':cfg['profile_url'] in [a['url'] for a in observed.get('authors', []) if a['name']==cfg['author_name']],
        'current_src_scheme':urlparse(observed.get('current_src', '')).scheme,
        'responses':responses}


def select_media(observed, media):
    sources = {observed.get('current_src'), *observed.get('sources', [])}
    exact = [m for m in media if m['src'] == observed.get('current_src')]
    if exact:
        return exact[-1]
    alternatives = [m for m in media if m['src'] in sources]
    if observed.get('video_count') == 1 and len({m['src'] for m in alternatives}) == 1:
        return alternatives[-1]
    # Only group renditions after actual append-to-player evidence. Matching
    # duration alone cannot establish ownership of a prefetched media object.
    if observed.get('video_count') == 1 and observed.get('current_src', '').startswith('blob:'):
        appended = {entry['src']:entry.get('type','') for entry in observed.get('appended_sources', [])}
        active = [dict(m, playback_type=appended[m['src']]) for m in media if m['src'] in appended]
        if active:
            active.sort(key=lambda m: (not m['playback_type'].startswith('audio/'),
                                      not m['content_type'].startswith('audio/')))
            chosen = dict(active[0])
            if chosen['playback_type'].startswith('audio/'):
                chosen['content_type'] = 'audio/mp4'
            return chosen
    return None


def media_url(url):
    parsed = urlparse(url)
    return parsed.scheme == 'https' and bool(parsed.hostname) and parsed.hostname.endswith('.douyinvod.com')


def capture(root, run_id, ids, *, allocated=None, record=True):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',run_id) or not all(str(aid).isdigit() for aid in ids):
        raise ValueError('Invalid run ID or video IDs')
    folder = root/'runs'/run_id
    folder.mkdir(parents=True, exist_ok=True)
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Explicit unique IDs required')
    allowed = {}
    for source_id, cfg in PROFILES.items():
        for work in retry_works(root, source_id, cfg, run_id=run_id):
            allowed[work['aweme_id']] = (source_id, cfg)
    if allocated is not None:
        source_id, works = allocated
        cfg = PROFILES[source_id]
        # The caller allocates before download, under the collection lock. New
        # works may not exist in the final store yet; require snapshot ownership.
        if len(works) > remaining_budget(root,source_id,run_id):
            raise ValueError('Playback allocation exceeds source quota')
        allowed = {str(w['aweme_id']):(source_id,cfg) for w in works
            if w.get('ownership_verified') and w.get('profile_url') == cfg['profile_url']
            and not w.get('review_only') and not w.get('access_label')
            and not excluded(source_id,str(w['aweme_id']))}
    if any(aid not in allowed for aid in ids):
        raise ValueError('ID not eligible: completed, restricted, unverified, cooling down or quota exceeded')
    results = []
    daily_lock = nullcontext() if allocated is not None and os.environ.get('QUANT_COLLECTION_LOCKED') == '1' else lock(root/'data/daily_collection.lock')
    with daily_lock, lock(root/'data/douyin_public_profile.lock'):
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(str(root/'data/browser_profiles/douyin'), headless=True)
            try:
                for aid in ids:
                    source_id, cfg = allowed[aid]
                    page = context.new_page()
                    page.add_init_script(TRACE_PLAYBACK)
                    media = []
                    responses = []
                    observed = {}
                    def observe(response):
                        # Observe only media fetched by the normal player, never API data.
                        ct = response.headers.get('content-type', '').split(';')[0].strip()
                        if media_url(response.url):
                            responses.append({'host':urlparse(response.url).hostname,
                                'path_hash':hashlib.sha256(urlparse(response.url).path.encode()).hexdigest()[:16],
                                'query_keys':sorted(parse_qs(urlparse(response.url).query)),
                                'mime_hint':(parse_qs(urlparse(response.url).query).get('mime_type') or [''])[0],
                                'resource_type':response.request.resource_type, 'status':response.status,
                                'content_type':ct})
                        exact_source = response.url in ([observed.get('current_src')] + observed.get('sources', []))
                        if ((response.request.resource_type in {'media', 'fetch', 'xhr'} or exact_source) and media_url(response.url)
                                and response.status in (200, 206)):
                            if ct.startswith(('audio/', 'video/')):
                                media.append({'src':response.url, 'content_type':ct,
                                    'resource_type':response.request.resource_type})
                    page.on('response', observe)
                    result = {'id':aid,'source_id':source_id}
                    try:
                        page.goto(f'https://www.douyin.com/video/{aid}',wait_until='domcontentloaded',timeout=45000)
                        deadline = time.monotonic()+30
                        while True:
                            observed = page.evaluate(READ_PLAYBACK)
                            chosen = select_media(observed, media)
                            reason = missing_playback_reason(observed, [chosen] if chosen else [])
                            if reason == 'media_response_missing' and media:
                                reason = 'media_response_ambiguous'
                            if reason in {'restricted_playback', 'verification_required', 'login_required'}:
                                raise RuntimeError(reason)
                            if observed['duration'] and observed['title'] and chosen:
                                break
                            if time.monotonic()>=deadline:
                                raise RuntimeError(reason or 'playback_not_ready')
                            page.wait_for_timeout(500)
                        if urlparse(observed['page_url']).path != f'/video/{aid}':
                            raise RuntimeError('playback_id_mismatch')
                        authors=[a['url'] for a in observed['authors'] if a['name']==cfg['author_name']]
                        if cfg['profile_url'] not in authors:
                            raise RuntimeError('Playback author not verified')
                        if re.search(r'会员专属|专属会员|会员专享|会员内容|会员可见|订阅专享|付费作品|付费内容|试看|购买本',observed['body']):
                            raise RuntimeError('Restricted playback marker; retain review_only')
                        # Audio responses from the active player take priority; sources
                        # exposed by the video element are the next exact attribution.
                        doc={'id':aid,'page_url':observed['page_url'],'title':observed['title'],
                             'authors':authors,'duration':observed['duration'],'restricted':False,
                             'src':chosen['src'],'media_content_type':chosen['content_type'],
                             'observed_at':datetime.now(timezone.utc).isoformat(),
                             'capture_method':'normal_playback_media_response'}
                        extension='.m4a' if chosen['content_type'].startswith('audio/') else '.mp4'
                        out=root/'data/douyin_media'/aid/('browser_playback'+extension)
                        staging=folder/('playback_'+aid+extension)
                        out.parent.mkdir(parents=True,exist_ok=True)
                        body = page.evaluate(DOWNLOAD_MEDIA, chosen['src'])
                        payload = base64.b64decode(body['body'], validate=True)
                        content_range = body['range']
                        if len(payload)<1024:
                            raise RuntimeError('Empty or invalid media body')
                        if content_range and (not content_range.startswith('bytes 0-') or int(content_range.split('/')[-1]) != len(payload)):
                            raise RuntimeError('Incomplete media response body')
                        staging.write_bytes(payload)
                        measured = subprocess.run(['/usr/bin/swift',str(root/'scripts/probe_media_duration.swift'),str(staging)],
                            capture_output=True,text=True,check=True,timeout=30)
                        probe = json.loads(measured.stdout)
                        actual_duration = float(probe['duration'])
                        if abs(actual_duration - observed['duration']) > 1:
                            raise RuntimeError('downloaded_media_duration_mismatch')
                        if not probe['audio_tracks']:
                            raise RuntimeError('downloaded_media_audio_track_missing')
                        # Public observation audit excludes signed media URLs.
                        audit = {k:v for k,v in doc.items() if k != 'src'}
                        with (folder/'browser_playback.jsonl').open('a') as manifest:
                            manifest.write(json.dumps(audit,ensure_ascii=False)+'\n')
                        staging.replace(out)
                        metadata=root/'data/douyin_metadata'/f'{aid}_data.json'
                        if metadata.exists():
                            backup=folder/'metadata_before'/metadata.name
                            backup.parent.mkdir(parents=True,exist_ok=True)
                            if not backup.exists(): backup.write_bytes(metadata.read_bytes())
                        metadata.write_text(json.dumps({'aweme_id':aid,'duration':observed['duration']*1000,
                            'desc':observed['title'],'capture_method':'authorized_browser_rendered_video',
                            'observed_url':observed['page_url'],'local_playback_audio':str(out.resolve()) if extension=='.m4a' else None},ensure_ascii=False))
                        if record:
                            record_attempt(root,source_id,aid,'awaiting_review',run_id=run_id)
                        result.update(status='awaiting_transcription',bytes=len(payload),duration=observed['duration'],verified_media_duration=actual_duration,media=str(out),sha256=hashlib.sha256(payload).hexdigest())
                    except Exception as exc:
                        # Avoid exposing signed media URLs in logs.
                        error=type(exc).__name__+': '+str(exc).split('https://')[0][:240]
                        if record:
                            record_attempt(root,source_id,aid,'pending_retry',error,run_id=run_id)
                        result.update(status='pending_retry',error=error)
                    finally:
                        diagnostic = safe_diagnostics(observed, responses[-80:], cfg)
                        diagnostic['appended_source_count'] = len(observed.get('appended_sources', []))
                        diagnostic['failure_stage'] = result.get('error')
                        diagnostic_path = folder/f'playback_diagnostic_{aid}.json'
                        diagnostic_path.write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2))
                        result['diagnostic_path'] = str(diagnostic_path)
                        page.close()
                    results.append(result)
                    print(json.dumps(result,ensure_ascii=False),flush=True)
            finally:
                context.close()
    result_name = f'playback_capture_{allocated[0]}.json' if allocated else 'playback_capture_result.json'
    (folder/result_name).write_text(json.dumps(results,ensure_ascii=False,indent=2))
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
