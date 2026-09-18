import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright
import douyin_group_collector as collector
from group_test_support import setup, window

class CollectorTests(unittest.TestCase):
    def test_profile_is_separate(self):
        self.assertEqual(collector.PROFILE, collector.ROOT/'data/browser_profiles/douyin_group')
    def test_real_dom_observer_rejects_wrong_group(self):
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page()
            page.set_content('<div>另一个群(500)</div><div class="messageMessageListlist"></div>')
            with self.assertRaises(Exception):page.evaluate(collector.observation_script())
            page.set_content('''<div>宇菠萝的认知圈1群(500)</div><div class="messageMessageListlist">
              <div data-index="0"><div class="messageMessageBoxmessageBox"><span class="MessageBoxMessageTitleavatarName">宇菠萝</span><div>群主</div><div class="MessageBoxTimetimeLayout">09/15 11:35</div><span class="MessageItemAudioduration">8"</span><span class="MessageItemAudiovoiceText">真实页面文字</span></div></div></div>''')
            observed=page.evaluate(collector.observation_script())
            self.assertTrue(observed['at_latest']);self.assertEqual(observed['messages'][0]['voice'],'真实页面文字')
            self.assertEqual(observed['messages'][0]['role'],'群主');browser.close()
    def test_save_preserves_checkpoint_and_resume(self):
        class Page:
            def evaluate(self,script):return window()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);setup(root)
            with patch.object(collector,'ROOT',root),patch.object(collector,'observation_script',return_value='observer'):
                worker=collector.Collector(Page(),'test')
                first=worker.save();self.assertFalse(first['ready'])
                resumed=collector.Collector(Page(),'test');second=resumed.save()
                self.assertTrue(second['ready']);self.assertEqual(second['raw_messages'],3)
                receipt=collector.prepare(root,'test');self.assertEqual(receipt['status'],'ready')
    def test_lock_rejects_concurrent_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'lock'
            with collector.lock(path):
                with self.assertRaises(RuntimeError):
                    with collector.lock(path):pass
    def test_neighbor_identity_changes_on_shift(self):
        a=[{'index':0,'text':'8"','duration':'8"'},{'index':1,'text':'anchor'}]
        b=[{'index':1,'text':'8"','duration':'8"'},{'index':2,'text':'anchor'}]
        self.assertNotEqual(collector.neighbors(a,0),collector.neighbors(b,0))
if __name__=='__main__':unittest.main()
