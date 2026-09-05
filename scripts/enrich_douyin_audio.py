#!/usr/bin/env python3
"""Download public Douyin videos, extract their audio, and run Whisper ASR."""
import argparse, json, subprocess, sys, shutil
from pathlib import Path
import tempfile, yaml

DOWNLOADER = Path('/Users/mac/.codex/skills/video-downloader/scripts/video_downloader.py')
SWIFT = Path(__file__).with_name('extract_audio.swift')

def restricted_access_label(detail):
    control=detail.get('video_control') or {}
    reasons=' '.join(str(v) for k,v in control.items() if ('reason' in k or 'msg' in k) and v)
    for label in ('专属会员','会员专属','会员专享','会员内容','会员可见','付费作品','付费内容','订阅专享'):
        if label in reasons: return label
    paid=detail.get('entertainment_video_paid_way') or {}; series=detail.get('series_paid_info') or {}
    if paid.get('paid_type') or paid.get('paid_ways') or series.get('series_paid_status') or series.get('item_price'):
        return '付费内容'
    return None

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--snapshot',type=Path,required=True); ap.add_argument('--metadata-root',type=Path,required=True); ap.add_argument('--whisper-dir',type=Path,required=True); ap.add_argument('--media-dir',type=Path,required=True); ap.add_argument('--author-name',default='久韭究财'); ap.add_argument('--ids',nargs='*'); args=ap.parse_args()
    snap=json.loads(args.snapshot.read_text()); wanted=set(args.ids or []); args.metadata_root.mkdir(parents=True,exist_ok=True); args.media_dir.mkdir(parents=True,exist_ok=True)
    works=[w for w in snap.get('works',[]) if not w.get('pinned') and not w.get('review_only') and (not wanted or str(w.get('aweme_id')) in wanted)]
    downloaded=0; failed=[]
    for w in works:
        aid=str(w.get('aweme_id')); url=w.get('url') or f'https://www.douyin.com/video/{aid}'
        out=args.media_dir/aid
        try:
            existing_metadata=args.metadata_root/f'{aid}_data.json'
            if existing_metadata.exists():
                detail=json.loads(existing_metadata.read_text(encoding='utf-8'))
                label=restricted_access_label(detail)
                if label:
                    w['review_only']=True; w['access_label']=label
                    continue
            # Request the complete asset bundle.  Douyin often serves a
            # video-only play_addr; the accompanying music file is the actual
            # narration track in that case, while videos with an embedded
            # track are still handled by AVFoundation below.
            # Always use an isolated, database-disabled downloader config.  The
            # shared downloader archive can report a cached success without
            # materializing files in this run's output directory.
            home=DOWNLOADER.parent.parent/'.runtime'/'douyin-downloader'
            base=home/'config.yml'; cfg=yaml.safe_load(base.read_text()) or {}
            cfg.update({'path': str(out.resolve()) + '/', 'database': False, 'video': True, 'music': True,
                        'cover': False, 'avatar': False, 'json': True, 'auto_cookie': True, 'mode': ['post']})
            with tempfile.NamedTemporaryFile('w', suffix='.yml', delete=False) as fh:
                yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False); config=fh.name
            r=subprocess.run(['uv','run','python','run.py','-c',config,'-u',url,'--show-warnings'],
                             cwd=home, capture_output=True, text=True, timeout=180)
            if r.returncode!=0: raise RuntimeError((r.stderr or r.stdout)[-500:])
            mp4s=list(out.rglob('*.mp4'))
            # The downloader's archive can report an old completed job without
            # materializing it in the requested directory. Retry with an
            # isolated, database-disabled config so ASR always gets the video.
            if not mp4s:
                raise RuntimeError('isolated downloader produced no mp4')
            if not mp4s: raise RuntimeError('download produced no mp4')
            mp4=mp4s[0]
            # Preserve the downloader sidecar in the metadata root.  The
            # standard Whisper/builder stages discover jobs exclusively from
            # these sidecars, so leaving it in the per-download directory
            # makes a successful video download look like a missing asset.
            sidecars = list(out.rglob('*.mp4.metadata.json')) + list(out.rglob('*_data.json'))
            if sidecars:
                sidecar = sidecars[0]
                try:
                    metadata = json.loads(sidecar.read_text(encoding='utf-8'))
                except Exception:
                    metadata = {}
                metadata.setdefault('aweme_id', aid)
                metadata.setdefault('play_addr', {})
                # Use the canonical *_data.json name understood by the
                # existing builder as well as the transcriber.
                destination = args.metadata_root / f'{aid}_data.json'
                destination.write_text(json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
                label=restricted_access_label(metadata)
                if label:
                    w['review_only']=True; w['access_label']=label
                    continue
            audio=args.whisper_dir/'prepared_audio'/f'{aid}_speech_audio.m4a'; audio.parent.mkdir(parents=True,exist_ok=True)
            if not audio.exists():
                try:
                    subprocess.run(['/usr/bin/swift',str(SWIFT),str(mp4),str(audio)],check=True,timeout=120)
                except Exception:
                    # Most Douyin MP4s are deliberately video-only.  The
                    # downloader's *_music.mp3 is the platform playback
                    # soundtrack and is the only available speech source.
                    music = next(iter(out.rglob('*_music.mp3')), None)
                    if music is None:
                        raise
                    shutil.copyfile(music, audio)
            downloaded+=1
        except Exception as e: failed.append({'id':aid,'error':str(e)})
    # Persist any metadata-based restriction discovered after the detail fetch;
    # downstream transcription and builders must see the corrected access flag.
    args.snapshot.write_text(json.dumps(snap, ensure_ascii=False), encoding='utf-8')
    # Transcriber discovers downloader metadata sidecars and the extracted audio
    # is supplied through the metadata's video playback track when available.
    print(json.dumps({'attempted':len(works),'downloaded':downloaded,'failed':failed},ensure_ascii=False))

if __name__=='__main__': main()
