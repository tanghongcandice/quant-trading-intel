import copy
import json
import sqlite3
import unittest
from app.services.x_revision import update_x_preview


class XRevisionTests(unittest.TestCase):
    def test_reviewed_legacy_suffix_requires_evidence_and_matching_prefix(self):
        conn = sqlite3.connect(':memory:')
        conn.execute('CREATE TABLE information_items(id TEXT,source_id TEXT,external_id TEXT,raw_json TEXT,content_text TEXT,content_hash TEXT,collected_at TEXT)')
        conn.execute('CREATE TABLE information_items_fts(item_id TEXT,content_text TEXT)')
        conn.execute('CREATE TABLE item_entities(item_id TEXT)')
        conn.execute('INSERT INTO information_items VALUES(?,?,?,?,?,?,?)', ('old','x_test','1','{}','原文','hash','date'))
        conn.execute('INSERT INTO information_items_fts VALUES(?,?)',('old','原文'))
        item={'id':'new','source':{'type':'x','id':'x_test'},'external':{'id':'1'},'content':{'text':'原文\n补回末段','hash':'hash2','language':'zh'},'timestamps':{'collected_at':'now'},'raw_payload':{}}
        self.assertFalse(update_x_preview(conn,item,'run'))
        item['raw_payload']['verified_detail_recovery']={'method':'rendered_detail_text_review','external_id':'1','evidence':'capture.jsonl'}
        mismatch=copy.deepcopy(item); mismatch['content']['text']='完全不同的另一篇文章'
        self.assertFalse(update_x_preview(conn,mismatch,'run'))
        self.assertTrue(update_x_preview(conn,item,'run'))
        self.assertEqual(item['id'],'old')
        self.assertFalse(update_x_preview(conn,item,'repeat'))
        conn.close()

    def test_translation_gate_and_identity(self):
        conn = sqlite3.connect(':memory:')
        conn.execute('CREATE TABLE information_items(id TEXT,source_id TEXT,external_id TEXT,raw_json TEXT,content_text TEXT,content_hash TEXT,collected_at TEXT)')
        conn.execute('CREATE TABLE information_items_fts(item_id TEXT,content_text TEXT)')
        conn.execute('CREATE TABLE item_entities(item_id TEXT)')
        old = {'raw_payload':{'source_truncated':True,'translation':'旧译文'}}
        conn.execute('INSERT INTO information_items VALUES(?,?,?,?,?,?,?)',('old','x_test','1',json.dumps(old),'Short','hash','date'))
        conn.execute('INSERT INTO information_items_fts VALUES(?,?)',('old','Short'))
        item = {'id':'new','source':{'type':'x','id':'x_test'},'external':{'id':'1'},
                'content':{'text':'Short but now complete.','hash':'newhash','language':'en'},
                'timestamps':{'collected_at':'newdate'},'raw_payload':{'tweet':{'source_truncated':False}}}
        with self.assertRaisesRegex(ValueError,'fresh Chinese'):
            update_x_preview(conn,copy.deepcopy(item),'run')
        item['raw_payload']['translation']='完整新译文'
        self.assertTrue(update_x_preview(conn,item,'run'))
        self.assertEqual(item['id'],'old')
        self.assertEqual(conn.execute('SELECT count(*) FROM x_revision_audit').fetchone()[0],1)
        self.assertFalse(update_x_preview(conn,item,'again'))
        conn.close()
