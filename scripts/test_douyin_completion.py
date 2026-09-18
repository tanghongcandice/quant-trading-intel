import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from check_douyin_completion import check
from app.jobs.collect_premarket import run_collection


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'db.sqlite'
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE information_items(source_id,external_id,raw_json)')
            db.execute('CREATE TABLE douyin_retry_attempts(source_id,external_id,attempts,next_retry,error)')

    def doc(self, status='pending_retry', sid='douyin_panyiyoudianshen'):
        return {'source':{'id':sid},'external':{'id':'1'},'content':{'title':'test'},
                'raw_payload':{'ownership':{'verified':True},'transcription':{'status':status}}}

    def save(self, doc):
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO information_items VALUES(?,?,?)',(doc['source']['id'],'1',json.dumps(doc)))

    def test_both_sources_pending_and_exhausted_are_not_success(self):
        for sid in ('douyin_panyiyoudianshen','douyin_jiujiujiucai'):
            self.save(self.doc(sid=sid))
            with sqlite3.connect(self.path) as db:
                db.execute('INSERT INTO douyin_retry_attempts VALUES(?,?,?,?,?)',(sid,'1',5,'2099','HTTP 403'))
        result=check(self.path)
        self.assertEqual(result['status'],'success_with_held_items')
        self.assertEqual(result['pending_transcription_count'],2)
        self.assertTrue(all(p['needs_attention'] for p in result['pending_transcription']))

    def test_members_and_complete_not_backlog(self):
        self.save(self.doc('member_title_only'))
        self.save(self.doc('complete','douyin_jiujiujiucai'))
        self.assertEqual(check(self.path)['status'],'success')

    def test_uncommitted_review_then_final_store_reconciliation(self):
        doc=self.doc('complete')
        review_path=self.root/'pending.jsonl'
        review_path.write_text(json.dumps(doc)+'\n')
        collection={'pending_review_path':str(review_path)}
        self.assertEqual(check(self.path,collection)['pending_transcription_count'],1)
        doc['raw_payload']['transcription']['text_refinement']={'status':'reviewed','reviewer':'codex'}
        self.save(doc)
        self.assertEqual(check(self.path,collection)['pending_transcription_count'],0)

    def test_cli_held_exit_code_and_report(self):
        self.save(self.doc())
        output=self.root/'completion.json'
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('check_douyin_completion.py')),
                               '--db',str(self.path),'--output',str(output)],capture_output=True)
        self.assertEqual(result.returncode,2)
        self.assertEqual(json.loads(output.read_text())['pending_transcription_count'],1)

    def test_scheduler_failure_not_masked_by_review_queue(self):
        items=self.root/'items.jsonl';items.write_text(json.dumps(self.doc('complete'))+'\n')
        summary={'status':'partial_failure','run_id':'test','items_path':str(items)}
        with patch('app.jobs.collect_premarket.subprocess.run',return_value=SimpleNamespace(
                returncode=1,stdout=json.dumps(summary),stderr='')), \
             patch('app.jobs.collect_premarket.import_jsonl',return_value=None):
            result=run_collection(db_path=self.path,run_id='test')
        self.assertEqual(result['pending_review_count'],1)
        self.assertEqual(result['status'],'partial_failure')


if __name__=='__main__': unittest.main()
