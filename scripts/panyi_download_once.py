"""One pending-batch download stage. Never retries or logs credentials."""
import argparse,fcntl,json,os,signal,subprocess,sys,threading,time,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--stage',choices=['metadata','video'],default='metadata'); args=ap.parse_args()
    with (ROOT/'data/panyi_backfill.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=json.loads((ROOT/'data/panyi_backfill_state.json').read_text())
        assert not state.get('blocked_reason')
        folder=Path(state['pending_batch']); manifest=json.loads((folder/'manifest.json').read_text())
        assert manifest['selected_ids']==[state['current_id']]
        aid=state['current_id']; report=folder/f'download_{args.stage}.json'
        assert not report.exists(), 'Stage already attempted; do not retry in this batch'
        assert not any(json.loads(f.read_text()).get('reason') for f in folder.glob('download_*.json')), 'Previous stage failed'
        result={'id':aid,'stage':args.stage,'started_at':time.time(),'reason':None,'status':'running'}
        report.write_text(json.dumps(result))
        out=folder/'metadata' if args.stage=='metadata' else folder/'media'/aid
        command=[sys.executable,'/Users/mac/.codex/skills/video-downloader/scripts/video_downloader.py','--non-interactive','download',f'https://www.douyin.com/video/{aid}','--backend','douyin','--audio-only' if args.stage=='metadata' else '--video-only','--output-dir',str(out)]
        proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
        def stop():
            try: os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError: pass
        timer=threading.Timer(180,stop); timer.start()
        try:
            for line in proc.stdout:
                reason=next((v for k,v in [('status=429','http_429'),('status=403','http_403'),('LoginRequiredError','login_required'),('验证码','captcha')] if k in line),None)
                if reason:
                    result['reason']=reason; stop(); break
            result['exit_code']=proc.wait(timeout=20)
        finally:
            timer.cancel()
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGKILL); proc.wait()
        files=list(out.rglob('*_data.json' if args.stage=='metadata' else '*.mp4'))
        if not result['reason'] and (result['exit_code'] or not files): result['reason']='download_error'
        result.update(status='failed' if result['reason'] else 'downloaded',finished_at=time.time(),file_count=len(files))
        report.write_text(json.dumps(result,indent=2)); print(json.dumps(result))
if __name__=='__main__': main()
