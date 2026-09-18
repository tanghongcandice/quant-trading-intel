"""Build reviewed-playback recovery candidates, never import before Codex review."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api'))
from app.jobs.build_douyin_profile_items import build_item, load_metadata
from prepare_douyin_ingestion import PROFILES


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True);args=parser.parse_args()
    folder=ROOT/'runs'/args.run_id
    observed={d['id']:d for d in map(json.loads,(folder/'browser_playback.jsonl').read_text().splitlines())}
    metadata=load_metadata(ROOT/'data/douyin_metadata');items=[];failed=[]
    with sqlite3.connect(ROOT/'data/quant_intel.sqlite') as db:
        for aid,evidence in observed.items():
            row=db.execute("SELECT source_id,raw_json FROM information_items WHERE source_type='douyin' AND external_id=?",(aid,)).fetchone()
            sid,raw=row;prior=json.loads(raw);cfg=PROFILES[sid]
            assert cfg['profile_url'] in evidence['authors'] and not evidence['restricted']
            work={'aweme_id':aid,'title':prior['content']['title'],'ownership_verified':True,
                  'profile_url':cfg['profile_url'],'retry_transcription':True}
            try:
                item=build_item(work,metadata,folder/'asr',datetime.now(timezone.utc).isoformat(),
                                source_id=sid,author_name=cfg['author_name'],
                                author_external_id=cfg['author_external_id'],profile_url=cfg['profile_url'])
                item['raw_payload']['ownership']['method']='authorized_browser_playback_author_link'
                item['raw_payload']['playback_evidence']=str(folder/'browser_playback.jsonl')
                item['timestamps']['created_at']=prior['timestamps']['created_at']
                items.append(item)
            except Exception as exc:failed.append({'id':aid,'error':str(exc)})
    (folder/'recovery_candidates.jsonl').write_text(''.join(json.dumps(i,ensure_ascii=False)+'\n' for i in items))
    (folder/'recovery_build_failures.json').write_text(json.dumps(failed,ensure_ascii=False,indent=2))
    print(json.dumps({'built':len(items),'failed':failed},ensure_ascii=False))


if __name__=='__main__':main()
