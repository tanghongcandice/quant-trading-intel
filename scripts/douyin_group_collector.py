#!/usr/bin/env python3
"""Dedicated, authorized Playwright group capture; rendered DOM only."""
import argparse
import fcntl
import json
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from playwright.sync_api import sync_playwright
from group_capture_checkpoint import checkpoint
from prepare_douyin_group_run import prepare
from group_retry_queue import attempt
import sqlite3
import chrome_preflight_diagnostics as diagnostics

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'data/browser_profiles/douyin_group'
GROUP = '宇菠萝的认知圈1群'
URL = 'https://www.douyin.com/chat'


def observation_script():
    # Share the existing DOM field contract with the manual CUA workflow.
    source = (ROOT/'scripts/douyin_group_browser_workflow.js').read_text()
    start = source.index('return tab.playwright.evaluate(() => {') + len('return tab.playwright.evaluate(')
    end = source.index('\n    });\n  }\n  async function save()', start)
    return source[start:end] + '\n    }'


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Collection/profile already in use; duplicate refused')
        yield


@contextmanager
def stage(run_id, name, attempt=1):
    token = diagnostics.begin(SimpleNamespace(root=ROOT, run_id=run_id, stage=name, attempt=attempt))['token']
    result = {'summary': 'Completed actual operation'}
    try:
        yield result
    except Exception as exc:
        diagnostics.end(SimpleNamespace(root=ROOT, run_id=run_id, token=token, status='error', summary=str(exc), details_json='{}'))
        raise
    else:
        diagnostics.end(SimpleNamespace(root=ROOT, run_id=run_id, token=token, status='success', summary=result['summary'], details_json='{}'))


def open_group(page):
    heading = page.get_by_text(re.compile(r'^宇菠萝的认知圈1群[（(]\d+[)）]$'))
    if not heading.count():
        entry = page.get_by_text(GROUP, exact=True)
        if entry.count() != 1:
            raise RuntimeError('Target group unavailable; login or group selection required')
        entry.click(timeout=5000)
    page.locator('.messageMessageListlist').wait_for(state='visible', timeout=15000)
    return page.evaluate(observation_script())


def neighbors(rows, index):
    return [(r['index'], r.get('text'), r.get('author'), r.get('duration'))
            for r in rows if abs(r['index']-index) <= 2]


class Collector:
    def __init__(self, page, run_id, max_steps=600, max_seconds=1200):
        self.page, self.run_id = page, run_id
        self.max_steps, self.deadline = max_steps, time.monotonic()+max_seconds
        self.window = None
        self.status = None
        self.voice_attempts = {}
        self.card_attempts = {}
        self.pending_resolution = None

    def save(self):
        observed = self.page.evaluate(observation_script())
        if self.pending_resolution:
            index, context, verified = self.pending_resolution
            if neighbors(observed['messages'], index) == context:
                for row in observed['messages']:
                    if row['index'] == index:
                        row['shared_video'] = verified
            self.pending_resolution = None
        self.status = checkpoint(ROOT, self.run_id, observed)
        self.window = observed
        return self.status

    def retry_key(self, row):
        matches = [e for e in self.status.get('retry_queue',{}).get('visible_candidates',[])
                   if row['index'] in e['indexes'] and not e['ambiguous']]
        return matches[0]['fingerprint'] if len(matches)==1 else None

    def record_attempt(self, fingerprint, error=None):
        if fingerprint:
            with sqlite3.connect(ROOT/'data/quant_intel.sqlite') as conn:
                attempt(conn,fingerprint,self.run_id,error)

    def resolve_card(self):
        pending = set(self.status.get('pending_video_indexes', []))
        row = next((r for r in self.window['messages'] if r['index'] in pending
                    and self.card_attempts.get(self.retry_key(r),0)<2), None)
        if not row:
            return False
        fp = self.retry_key(row)
        if not fp or self.card_attempts.get(fp,0)>=2:
            return False
        fresh = self.page.evaluate(observation_script())
        if neighbors(fresh['messages'],row['index']) != neighbors(self.window['messages'],row['index']):
            self.save()
            return True
        message=self.page.locator(f'[data-index="{row["index"]}"] .messageMessageBoxmessageBox')
        if message.count()!=1 or message.inner_text(timeout=2000)!=row['text']:
            self.save()
            return True
        self.card_attempts[fp]=self.card_attempts.get(fp,0)+1
        before=set(self.page.context.pages)
        original_url=self.page.url
        error=None
        try:
            message.locator('.MessageItemShareAwemecontainer').click(timeout=5000)
            for _ in range(10):
                self.page.wait_for_timeout(500)
                opened=[p for p in self.page.context.pages if p not in before]
                target=opened[-1] if opened else self.page
                url=target.url
                match=re.search(r'(?:/video/|[?&]modal_id=)(\d+)',url) if re.match(r'^https://(?:www\.)?douyin\.com/',url) else None
                if match:
                    # Metadata from the rendered card and the observed playback URL.
                    title=row.get('text','').strip()
                    for prefix in (row.get('time'),row.get('author'),row.get('role')):
                        if prefix:title=title.removeprefix(prefix).strip()
                    self.pending_resolution=(row['index'], neighbors(fresh['messages'],row['index']), {
                        'url':'https://www.douyin.com/video/'+match[1],
                        'observed_url':url,'title':title,'verification':'opened_original_card'})
                    break
            else:
                raise RuntimeError('Original card opened but no observed video URL; retain for retry')
        except Exception as exc:
            error=str(exc)
        finally:
            for opened in list(self.page.context.pages):
                if opened not in before:opened.close()
            if self.page.url!=original_url:
                self.page.go_back(wait_until='domcontentloaded',timeout=15000)
            else:
                self.page.keyboard.press('Escape')
            self.record_attempt(fp,error)
            self.save()
        return True

    def transcribe(self):
        pending = set(self.status['pending_voice_indexes'])
        def segment_key(r):
            candidates=self.status.get('retry_queue',{}).get('visible_candidates',[])
            batch=next((b for b in candidates if r['index'] in b['indexes'] and not b['ambiguous']),None)
            return (batch['fingerprint'],batch['indexes'].index(r['index'])) if batch else None
        row = next((r for r in reversed(self.window['messages']) if r['index'] in pending
                    and not r.get('voice') and segment_key(r) is not None
                    and self.voice_attempts.get(segment_key(r),0)<2), None)
        if not row:
            return False
        fp = self.retry_key(row)
        key = segment_key(row)
        if self.voice_attempts.get(key, 0) >= 2:
            return False
        fresh = self.page.evaluate(observation_script())
        if neighbors(fresh['messages'], row['index']) != neighbors(self.window['messages'], row['index']):
            self.save()
            return True
        message = self.page.locator(f'[data-index="{row["index"]}"] .messageMessageBoxmessageBox')
        # Playwright has_text matches textContent; the captured contract uses
        # innerText (including rendered line breaks). Compare like with like.
        if message.count()!=1 or message.inner_text(timeout=2000)!=row['text']:
            self.save()
            return True
        self.voice_attempts[key] = self.voice_attempts.get(key, 0)+1
        message.locator('.MessageItemAudioaudioBox').click(button='right', timeout=5000)
        menu = self.page.get_by_text('转文字', exact=True)
        error=None
        try:
            menu.wait_for(state='visible', timeout=2000)
            menu.click(timeout=3000)
            # Do not wait on a stale index. Re-observe and persist every result.
            for _ in range(12):
                self.page.wait_for_timeout(500)
                self.save()
                if row['index'] not in self.status['pending_voice_indexes']:
                    break
                current = next((r for r in self.window['messages'] if r['index']==row['index']), None)
                if not current or current.get('duration') != row.get('duration') or current.get('author') != row.get('author'):
                    break
            if row['index'] in self.status['pending_voice_indexes']:
                error='Native transcription still pending after observation; retry next run'
        except Exception as exc:
            error=str(exc)
        finally:
            self.page.keyboard.press('Escape')
            self.save()
            self.record_attempt(fp,error)
        return True

    def scroll(self, older):
        self.save()
        x,y = self.window['scroll_target']
        self.page.mouse.move(x,y)
        self.page.mouse.wheel(0, -450 if older else 450)
        self.page.wait_for_timeout(600)
        self.save()

    def run(self):
        self.save()
        unchanged = 0
        for _ in range(self.max_steps):
            if time.monotonic() >= self.deadline:
                raise RuntimeError('Group time budget reached; checkpoint retained')
            if self.status['ready']:
                return self.status
            if self.transcribe():
                continue
            if self.resolve_card():
                continue
            errors = self.status['errors']
            older = any(any(word in e for word in ('overlap', 'coverage', 'boundary', 'Oldest')) for e in errors)
            if not older and (self.status['pending_voice_count'] or self.status.get('pending_video_indexes')):
                visible = {r['index'] for r in self.window['messages']}
                pending = []
                for entry in self.status.get('retry_queue',{}).get('visible_candidates',[]):
                    if not entry['pending'] or entry['ambiguous']: continue
                    for pos,index in enumerate(entry['indexes']):
                        tries = self.card_attempts.get(entry['fingerprint'],0) if entry['kind']=='card' else self.voice_attempts.get((entry['fingerprint'],pos),0)
                        if tries < 2 and index not in visible: pending.append(index)
                older = bool(pending) and max(pending) > max(visible)
            before = [(r['index'],r.get('text')) for r in self.window['messages']]
            if not older and self.window['at_latest']:
                self.page.wait_for_timeout(600)
                self.save()
                if self.status['ready']:
                    return self.status
                raise RuntimeError('Remaining group gaps: '+'; '.join(self.status['errors']))
            self.scroll(older)
            after = [(r['index'],r.get('text')) for r in self.window['messages']]
            unchanged = unchanged+1 if before==after else 0
            if unchanged >= 3:
                raise RuntimeError('Group scroll made no progress; checkpoint retained')
        raise RuntimeError('Group step budget reached; checkpoint retained')


def collect(args):
    folder = ROOT/'runs'/args.run_id; folder.mkdir(parents=True, exist_ok=True)
    errors=[]; receipt=None
    with sync_playwright() as pw:
        with stage(args.run_id, 'chrome_tab_enumeration') as result:
            context = pw.chromium.launch_persistent_context(str(PROFILE), headless=not args.headed, channel='chrome')
            result['summary']='Dedicated group profile launched; no daily Chrome profile access'
        try:
            page=context.pages[0] if context.pages else context.new_page()
            for attempt in range(1,4):
                try:
                    with stage(args.run_id,'group_dom_read',attempt) as result:
                        page.goto(URL,wait_until='domcontentloaded',timeout=30000)
                        page.wait_for_timeout(2000)
                        open_group(page)
                        with stage(args.run_id,'processing_ledger_reuse') as reuse_result:
                            worker=Collector(page,args.run_id,args.max_steps,args.max_seconds)
                            status=worker.save()
                            reuse_result['summary']=json.dumps(status,ensure_ascii=False)
                        status=worker.run()
                        result['summary']=json.dumps(status,ensure_ascii=False)
                    break
                except Exception as exc:
                    errors.append(str(exc))
                    # Only reconnect before any actual window capture. Never
                    # repeat the full processing budget after partial progress.
                    if (folder/'group_checkpoint.json').exists() or attempt==3:
                        break
                    page.wait_for_timeout(3000 if attempt==1 else 10000)
        finally:
            context.close()
    try:
        with stage(args.run_id,'group_receipt') as result:
            receipt=prepare(ROOT,args.run_id)
            result['summary']=json.dumps(receipt,ensure_ascii=False)
    except Exception as exc:
        errors.append(str(exc))
    validation=diagnostics.validate(SimpleNamespace(root=ROOT,run_id=args.run_id))
    status='success' if receipt and receipt['status']=='ready' and validation['ready'] else 'partial_failure'
    result={'run_id':args.run_id,'status':status,'errors':errors,'receipt':receipt,'validation':validation}
    (folder/'group_collector_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


def login(args):
    with sync_playwright() as pw:
        context=pw.chromium.launch_persistent_context(str(PROFILE),headless=False,channel='chrome')
        try:
            page=context.pages[0] if context.pages else context.new_page()
            page.goto(URL,wait_until='domcontentloaded',timeout=45000)
            print('请在专用浏览器登录抖音并打开目标群；不读取或输出凭据。',flush=True)
            deadline=time.monotonic()+args.wait_seconds
            while time.monotonic()<deadline:
                try:
                    observed=open_group(page)
                    if observed['messages']:
                        print(json.dumps({'status':'authenticated_group_verified','group':GROUP,'visible_messages':len(observed['messages'])},ensure_ascii=False),flush=True)
                        return 0
                except Exception:
                    pass
                page.wait_for_timeout(2000)
            print(json.dumps({'status':'login_required','group':GROUP},ensure_ascii=False),flush=True)
            return 2
        finally:
            context.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['login','collect'])
    parser.add_argument('--run-id',default=os.environ.get('QUANT_RUN_ID'))
    parser.add_argument('--headed',action='store_true')
    parser.add_argument('--wait-seconds',type=int,default=600)
    parser.add_argument('--max-steps',type=int,default=600)
    parser.add_argument('--max-seconds',type=int,default=1200)
    parser.add_argument('--activate',action='store_true',help='Enable daily entry only after a fully verified live capture')
    args=parser.parse_args()
    if args.command=='collect' and (not args.run_id or not re.fullmatch('[A-Za-z0-9_-]+',args.run_id)):
        parser.error('Valid --run-id required')
    with lock(ROOT/'data/douyin_group_profile.lock'):
        if args.command=='login':
            raise SystemExit(login(args))
        if os.environ.get('QUANT_COLLECTION_LOCKED')=='1':
            result=collect(args)
        else:
            with lock(ROOT/'data/daily_collection.lock'):
                result=collect(args)
        print(json.dumps(result,ensure_ascii=False))
        if args.activate and result['status']=='success':
            marker=ROOT/'data/collection_state/douyin_group_script_enabled.json'
            marker.parent.mkdir(parents=True,exist_ok=True)
            marker.write_text(json.dumps({'run_id':args.run_id,'validated_at':datetime.now(timezone.utc).isoformat(),'profile':str(PROFILE)}))
        raise SystemExit(0 if result['status']=='success' else 2)

if __name__=='__main__':
    main()
