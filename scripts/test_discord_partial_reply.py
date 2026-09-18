import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'packages/ingestion_scheduler/src'))
from ingestion_scheduler.adapters.discord import DiscordAdapter

class PartialReplyTests(unittest.TestCase):
    def setUp(self):
        self.source={'target_author_ids':['42']}
        self.reply={'id':'2','timestamp':'2026-09-17T10:00:00Z','author':{'id':'42'},'reference':{'messageId':'1'},'referencedMessage':{'id':'1','content':'Original message','author':{'displayName':None}}}
    def test_missing_parent_metadata_stays_embedded(self):
        reply=copy.deepcopy(self.reply)
        result=DiscordAdapter()._filter_docs(self.source,[reply])
        self.assertEqual([d['id'] for d in result],['2'])
        self.assertEqual(result[0]['referencedMessage'],self.reply['referencedMessage'])
        self.assertNotIn('timestamp',result[0]['referencedMessage'])
    def test_observed_parent_keeps_own_time_and_context_isolation(self):
        reply=copy.deepcopy(self.reply)
        reply['referencedMessage'].update(timestamp='2026-09-16T09:00:00Z',author={'id':'99'})
        result=DiscordAdapter()._filter_docs(self.source,[reply])
        self.assertEqual(result[0]['timestamp'],'2026-09-16T09:00:00Z')
        self.assertTrue(result[0]['_context_only'])
        self.assertEqual(result[0]['author']['id'],'99')
if __name__=='__main__':unittest.main()
