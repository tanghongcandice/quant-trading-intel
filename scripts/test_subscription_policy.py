import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api'))
from app.services.subscription_policy import enforce_subscription_policy

class SubscriptionTests(unittest.TestCase):
    def test_preview(self):
        for source in ('x', 'douyin'):
            item={'source':{'type':source},'raw_payload':{'subscription_preview':True},'entities':[{}]}
            enforce_subscription_policy(item)
            self.assertFalse(item['raw_payload']['analysis_policy']['include'])
            self.assertEqual(item['entities'], [])

    def test_substack_and_ellipsis_not_excluded(self):
        for item in ({'source':{'type':'substack'},'raw_payload':{'subscription_preview':True}},
                     {'source':{'type':'x'},'content':{'text':'Long text…'}}):
            enforce_subscription_policy(item)
            self.assertNotIn('analysis_policy',item.get('raw_payload',{}))

    def test_helper_evidence(self):
        item={'source':{'type':'x'},'raw_payload':{'tweet':{'subscription_preview':True}}}
        enforce_subscription_policy(item)
        self.assertFalse(item['raw_payload']['analysis_policy']['include'])

if __name__=='__main__': unittest.main()
