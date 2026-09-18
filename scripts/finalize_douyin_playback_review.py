"""Apply an explicit per-item Codex review log to playback-recovery candidates.

This does not perform review and does not import: the reviewer must first read
each complete transcript and supply codex_review.json with corrections/notes.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api'))
from app.jobs.repair_douyin_transcripts import content_hash, review_a_share_terms


def finalize(folder):
    reviews = json.loads((folder / 'codex_review.json').read_text())
    docs = [json.loads(line) for line in (folder / 'recovery_candidates.jsonl').read_text().splitlines()]
    expected = {json.loads(line)['id'] for line in (folder / 'browser_playback.jsonl').read_text().splitlines()}
    assert expected == {d['external']['id'] for d in docs} == set(reviews), 'Missing candidates or explicit reviews'
    audit = []
    for item in docs:
        aid = item['external']['id']; review = reviews[aid]
        assert review.get('notes'), f'{aid}: missing review notes'
        trans = item['raw_payload']['transcription']
        assert trans['status'] == 'complete'
        assert trans['media_duration_seconds'] > 0
        assert trans['transcript_end_seconds'] >= trans['media_duration_seconds'] - 8
        before = item['content']['text']; text = before; changes = []
        for old, new in review['corrections'].items():
            count = text.count(old)
            if count:
                text = text.replace(old, new)
                changes.append({'pattern':old,'replacement':new,'count':str(count)})
        item['content']['text'] = text
        item['content']['hash'] = content_hash(item['content']['title'], text)
        item['raw_payload']['a_share_term_review'] = review_a_share_terms(item['content']['title'], text, tuple(changes))
        trans['text_refinement'] = {'status':'reviewed','reviewer':'codex','method':'full_text_context_review',
            'corrections':changes,'notes':review['notes'],'preserve_claims':True,
            'numeric_policy':'Retain source values; annotate ambiguous units/number runs. ASR duplicate removals logged.',
            'review_evidence':str(folder / 'codex_review.json')}
        audit.append({'id':aid,'source_id':item['source']['id'],'title':item['content']['title'],
                      'before_text':before,'after_text':text,'changes':changes,
                      'duration':trans['media_duration_seconds'],'end':trans['transcript_end_seconds']})
    (folder / 'reviewed_recovery.jsonl').write_text(''.join(json.dumps(d,ensure_ascii=False)+'\n' for d in docs))
    (folder / 'review_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    print(json.dumps({'reviewed':len(docs),'output':str(folder / 'reviewed_recovery.jsonl')},ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--run-id', required=True)
    finalize(ROOT / 'runs' / parser.parse_args().run_id)
