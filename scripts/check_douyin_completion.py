"""Audit final-store transcript backlog; never count title placeholders as done."""
import argparse
import json
import sqlite3
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api'))
from app.services.douyin_access_policy import excluded

SOURCES = {'douyin_jiujiujiucai', 'douyin_panyiyoudianshen'}
PENDING = {'pending_retry', 'no_audio_title_only', 'no_speech_title_only', 'reviewed_truncated'}


def check(db_path, collection=None):
    pending = []
    with sqlite3.connect(f'file:{Path(db_path).resolve()}?mode=ro', uri=True) as db:
        attempts = {}
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='douyin_retry_attempts'").fetchone():
            attempts = {(sid, aid): (n, next_retry, error) for sid, aid, n, next_retry, error in
                        db.execute('SELECT source_id,external_id,attempts,next_retry,error FROM douyin_retry_attempts')}
        for sid, aid, raw in db.execute('SELECT source_id,external_id,raw_json FROM information_items WHERE source_id IN (?,?)', tuple(SOURCES)):
            if excluded(sid, aid): continue
            doc = json.loads(raw); payload = doc.get('raw_payload') or {}
            trans = payload.get('transcription') or {}
            if trans.get('status') not in PENDING or payload.get('access_label') or payload.get('subscription_preview'):
                continue
            count, next_retry, error = attempts.get((sid, aid), (0, None, None))
            ownership = payload.get('ownership') or {}
            pending.append({'source_id':sid, 'id':aid, 'title':doc.get('content',{}).get('title'),
                            'status':trans['status'], 'attempts':count, 'next_retry':next_retry,
                            'needs_attention':count >= 5 or not ownership.get('verified'),
                            'error':error or trans.get('error')})
        review_path = (collection or {}).get('pending_review_path')
        if review_path:
            for line in Path(review_path).read_text().splitlines():
                doc = json.loads(line); sid = doc['source']['id']; aid = doc['external']['id']
                if excluded(sid, aid): continue
                if sid not in SOURCES:
                    continue
                row = db.execute('SELECT raw_json FROM information_items WHERE source_id=? AND external_id=?',(sid,aid)).fetchone()
                saved = json.loads(row[0]) if row else {}
                trans = (saved.get('raw_payload') or {}).get('transcription') or {}
                review = trans.get('text_refinement') or {}
                if trans.get('status')=='complete' and review.get('status')=='reviewed' and review.get('reviewer')=='codex':
                    continue
                if not any(p['source_id']==sid and p['id']==aid for p in pending):
                    pending.append({'source_id':sid,'id':aid,'title':doc['content'].get('title'),
                                    'status':'pending_codex_review','needs_attention':True})
    return {'status':'success_with_held_items' if pending else 'success',
            'pending_transcription_count':len(pending),'pending_transcription':pending}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--collection-json',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    collection = json.loads(args.collection_json.read_text()) if args.collection_json else None
    result = check(args.db,collection)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(2 if result['pending_transcription_count'] else 0)


if __name__=='__main__': main()
