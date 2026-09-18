import json
import sqlite3
import unittest
from app.services.group_retry_queue import observe, close_committed, attempt, SOURCE


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE information_items(id TEXT,source_id TEXT,external_id TEXT,raw_json TEXT)')
        self.entry = dict(fingerprint='a',kind='voice',pending=True,context={'time':'test'})
        observe(self.db,[self.entry],'first')
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def state(self):
        return self.db.execute('SELECT status FROM group_retry_queue').fetchone()[0]

    def test_absence_does_not_resolve(self):
        observe(self.db,[],'next')
        self.assertEqual(self.state(),'pending')

    def test_capture_not_import(self):
        observe(self.db,[dict(self.entry,pending=False)],'next')
        self.assertEqual(self.state(),'awaiting_import')

    def test_commit_evidence_and_rollback(self):
        item={'source':{'id':SOURCE},'external':{'id':'one'},'raw_payload':{
            'message_parts':[{'voice':'real transcript'}],'group_retry_keys':['a']}}
        close_committed(self.db,item)
        self.assertEqual(self.state(),'pending')
        wrong=json.loads(json.dumps(item)); wrong['raw_payload']['message_parts'][0]['voice']='wrong'
        self.db.execute('INSERT INTO information_items VALUES(?,?,?,?)',('id',SOURCE,'one',json.dumps(wrong)))
        close_committed(self.db,item)
        self.assertEqual(self.state(),'pending')
        self.db.execute('UPDATE information_items SET raw_json=?',(json.dumps(item),))
        close_committed(self.db,item)
        self.assertEqual(self.state(),'resolved')
        self.db.rollback()
        self.assertEqual(self.state(),'pending')

    def test_attempt_audit(self):
        attempt(self.db,'a','next','timeout')
        self.assertEqual(self.db.execute('SELECT attempts,last_error FROM group_retry_queue').fetchone(),(1,'timeout'))

if __name__ == '__main__': unittest.main()
