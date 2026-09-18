import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from douyin_retry import retry_works, record_attempt
from app.services.douyin_revision import update_profile_transcript
from app.jobs.collect_premarket import _requires_codex_review


class RetryTests(unittest.TestCase):
    def test_both_sources_retry_old_incomplete_but_not_members_or_complete(self):
        for sid in ['douyin_jiujiujiucai','douyin_panyiyoudianshen']:
            with self.subTest(source=sid), tempfile.TemporaryDirectory() as folder:
                root=Path(folder); (root/'data').mkdir(); db=sqlite3.connect(root/'data/quant_intel.sqlite')
                db.execute('CREATE TABLE information_items(source_id,external_id,raw_json,created_at)')
                for idx,status in enumerate(['no_audio_title_only','complete','member_title_only']):
                    doc={'external':{'id':str(idx),'url':'https://example.com'},'content':{'title':'title'},
                         'timestamps':{'created_at':'2020-01-01T00:00:00Z'},'raw_payload':{
                             'ownership':{'verified':True,'profile_url':'profile'},'transcription':{'status':status}}}
                    db.execute('INSERT INTO information_items VALUES(?,?,?,?)',(sid,str(idx),json.dumps(doc),'2020'))
                db.commit(); db.close()
                self.assertEqual([w['aweme_id'] for w in retry_works(root,sid,{'profile_url':'profile'})],['0'])
                record_attempt(root,sid,'0','pending_retry','HTTP 403')
                self.assertEqual(retry_works(root,sid,{'profile_url':'profile'}),[])
                self.assertEqual(len(retry_works(root,sid,{'profile_url':'profile'},force=True)),1)
                self.assertEqual(retry_works(root,sid,{'profile_url':'profile'},limit=0,force=True),[])
                self.assertEqual(retry_works(root,sid,{'profile_url':'wrong'},force=True),[])
                for _ in range(4):
                    record_attempt(root,sid,'0','pending_retry','HTTP 403')
                with sqlite3.connect(root/'data/quant_intel.sqlite') as db:
                    db.execute("UPDATE douyin_retry_attempts SET next_retry='2000-01-01'")
                self.assertEqual(retry_works(root,sid,{'profile_url':'profile'}),[])

    def test_review_gate_identity_audit_and_idempotence(self):
        db=sqlite3.connect(':memory:')
        db.execute('CREATE TABLE information_items(id,source_id,external_id,raw_json,created_at,content_text,content_hash,collected_at)')
        for table in ['information_items_fts','item_entities','item_analysis']:
            db.execute(f'CREATE TABLE {table}(item_id,content_text)')
        old={'raw_payload':{'transcription':{'status':'no_audio_title_only'},'ownership':{'verified':True,'profile_url':'profile'}}}
        db.execute('INSERT INTO information_items VALUES(?,?,?,?,?,?,?,?)',('stable','douyin_panyiyoudianshen','1',json.dumps(old),'original','pending','oldhash','old'))
        db.execute('INSERT INTO information_items_fts VALUES(?,?)',('stable','pending'))
        item={'id':'different','source':{'id':'douyin_panyiyoudianshen'},'external':{'id':'1'},
              'timestamps':{'created_at':'wrong','collected_at':'now'},'content':{'text':'完整转录','hash':'hash'},
              'raw_payload':{'ownership':{'verified':True,'profile_url':'profile'},'a_share_term_review':{'status':'passed'},
                             'transcription':{'status':'complete','text_refinement':{'status':'pending_codex_review'}}}}
        self.assertTrue(_requires_codex_review(item))
        with self.assertRaisesRegex(ValueError,'Codex review'):
            update_profile_transcript(db,copy.deepcopy(item),'run')
        item['raw_payload']['transcription']['text_refinement']={'status':'reviewed','reviewer':'codex'}
        self.assertTrue(update_profile_transcript(db,item,'run'))
        self.assertEqual(item['id'],'stable'); self.assertEqual(item['timestamps']['created_at'],'original')
        self.assertFalse(update_profile_transcript(db,item,'again'))
        self.assertEqual(db.execute('SELECT count(*) FROM douyin_revision_audit').fetchone()[0],1)
        self.assertEqual(db.execute('SELECT content_text FROM information_items_fts').fetchone()[0],'完整转录')

    def test_builder_marks_failed_download_pending_not_audio_absent(self):
        from app.jobs.build_douyin_profile_items import build_item
        doc=build_item({'aweme_id':'7686053653108014051','title':'公开作品','no_audio':True,
                        'transcription_error':'metadata_missing http=403','ownership_verified':True,'profile_url':'profile'},
                       {},Path('/unused'),'now',source_id='douyin_panyiyoudianshen',author_name='潘姨',
                       author_external_id='author',profile_url='profile')
        self.assertEqual(doc['raw_payload']['transcription']['status'],'pending_retry')
        self.assertIn('403',doc['raw_payload']['transcription']['error'])
        self.assertFalse(doc['raw_payload']['analysis_policy']['include'])
        self.assertNotIn('无可转录音轨',doc['content']['text'])

    def test_review_gate_requires_actual_reviewer_for_both_profiles(self):
        for sid in ['douyin_jiujiujiucai','douyin_panyiyoudianshen']:
            doc={'source':{'id':sid},'raw_payload':{'transcription':{
                'status':'complete','text_refinement':{'status':'reviewed'}}}}
            self.assertTrue(_requires_codex_review(doc))
            doc['raw_payload']['transcription']['text_refinement']['reviewer']='codex'
            self.assertFalse(_requires_codex_review(doc))


if __name__=='__main__':
    unittest.main()
