import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright
import douyin_group_collector as collector
from group_test_support import setup, window

class CollectorTests(unittest.TestCase):
    def test_initial_hydration_settles_before_identity_is_committed(self):
        from unittest.mock import Mock
        transient = {'messages':[{'index':17,'author':'管理员','duration':'12"'}], 'at_latest':True}
        stable = {'messages':[{'index':17,'author':'','duration':'12"'},
                              {'index':18,'author':'管理员','text':'边界'}], 'at_latest':True}
        page = Mock()
        page.evaluate.side_effect = [transient, transient, stable, stable, stable, stable]
        self.assertEqual(collector.settled_observation(page),stable)
        self.assertEqual(page.evaluate.call_count,6)

    def test_unstable_initial_dom_is_rejected(self):
        from unittest.mock import Mock
        page = Mock()
        page.evaluate.side_effect = [{'messages':[{'index':i}], 'at_latest':True} for i in range(4)]
        with self.assertRaisesRegex(RuntimeError,'did not settle'):
            collector.settled_observation(page,max_observations=4)

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

    def test_open_group_waits_for_dynamic_counted_heading(self):
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page()
            page.set_content('<div id="root"></div>')
            page.evaluate("""setTimeout(() => {
              document.querySelector('#root').innerHTML = `<div>宇菠萝的认知圈1群(500)</div>
                <div class="messageMessageListlist"><div data-index="0"><div class="messageMessageBoxmessageBox">
                <span class="MessageBoxMessageTitleavatarName">宇菠萝</span><div>群主</div>
                <div class="MessageBoxTimetimeLayout">09/18 12:06</div><span>测试消息</span>
                </div></div></div>`;
            }, 100)""")
            observed=collector.open_group(page)
            self.assertEqual(observed['group_name'],'宇菠萝的认知圈1群')
            self.assertEqual(observed['messages'][0]['author'],'宇菠萝')
            browser.close()
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
    def test_partial_activation_requires_authorization_and_latest_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'runs'/'test';folder.mkdir(parents=True)
            evidence={'latest_checked':True,'final_db_cursor':'2026-09-16T12:12:00+08:00',
                      'earliest_checked':'2026-09-17T21:01:00+08:00'}
            (folder/'group_checkpoint.json').write_text(json.dumps({'collection_evidence':evidence}))
            result={'run_id':'test','status':'partial_failure','validation':{'ready':True},
                    'receipt':{'status':'partial_ready','built_items':4,'pending_errors':['overlap not reached']}}
            with patch.object(collector,'ROOT',root):
                with self.assertRaises(ValueError):collector.activate(result)
                marker=collector.activate(result,allow_partial=True)
                self.assertFalse(marker['coverage_complete'])
                self.assertEqual(marker['history_gap']['frozen_final_cursor'],evidence['final_db_cursor'])
                self.assertEqual(marker['history_gap']['status'],'unresolved')
                result['validation']['ready']=False
                with self.assertRaises(ValueError):collector.activate(result,allow_partial=True)
                result['validation']['ready']=True;evidence['latest_checked']=False
                (folder/'group_checkpoint.json').write_text(json.dumps({'collection_evidence':evidence}))
                with self.assertRaises(ValueError):collector.activate(result,allow_partial=True)
if __name__=='__main__':unittest.main()
