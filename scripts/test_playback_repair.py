import copy
import unittest
from unittest.mock import patch
from capture_douyin_playback import media_url, capture
from reconcile_group_retry_evidence import verified_shift


class PlaybackTests(unittest.TestCase):
    def test_only_observed_media_host_is_accepted(self):
        self.assertTrue(media_url('https://v3.douyinvod.com/video/actual'))
        for url in ('blob:https://www.douyin.com/abc','https://douyinvod.com.evil.test/a',
                    'http://v3.douyinvod.com/a','https://www.douyin.com/aweme/api'):
            self.assertFalse(media_url(url))

    def test_ineligible_id_fails_before_browser_launch(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp, patch('capture_douyin_playback.retry_works',return_value=[]), patch('capture_douyin_playback.sync_playwright') as browser:
            with self.assertRaisesRegex(ValueError,'not eligible'):
                capture(Path(tmp),'test',['123'])
            browser.assert_not_called()


class RetryReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.old={'messages':[
            {'index':0,'duration':'8"','voice':'','text':'8"'},
            {'index':1,'duration':'','text':'12:01\n某成员加入了群聊', 'time':'12:01','resolved_time':'2026-09-18T12:01:00+08:00'},
            {'index':2,'duration':'7"','text':'7"'},
            {'index':3,'duration':'3"','text':'20分钟前\n甲\n管理员\n3"','time':'20分钟前','author':'甲','role':'管理员'}]}
        self.fresh=copy.deepcopy(self.old)
        for r in self.fresh['messages']:r['index']+=2
        self.fresh['messages'][-1].update(author='',role='',time='',text='3"\n新原生转写',voice='新原生转写')
        self.parts={5:{'speaker':'甲','sender_role':'管理员'}}

    def test_header_hydration_with_dated_text_anchor(self):
        self.assertEqual(verified_shift(self.old,self.fresh,self.parts),2)

    def test_durations_alone_do_not_resolve(self):
        self.old['messages'][1].update(text='12:01')
        self.fresh['messages'][1].update(text='12:01')
        with self.assertRaises(ValueError):verified_shift(self.old,self.fresh,self.parts)

    def test_wrong_committed_author_does_not_resolve(self):
        self.parts[5]['speaker']='乙'
        with self.assertRaises(ValueError):verified_shift(self.old,self.fresh,self.parts)

    def test_different_day_does_not_resolve(self):
        self.fresh['messages'][1]['resolved_time']='2026-09-17T12:01:00+08:00'
        with self.assertRaises(ValueError):verified_shift(self.old,self.fresh,self.parts)

    def test_changed_existing_transcript_does_not_resolve(self):
        self.old['messages'][0]['voice']='原观察'
        self.fresh['messages'][0]['voice']='不同内容'
        with self.assertRaises(ValueError):verified_shift(self.old,self.fresh,self.parts)

    def test_ambiguous_overlap_does_not_resolve(self):
        repeated=copy.deepcopy(self.fresh['messages'])
        for r in repeated:r['index']+=10
        self.fresh['messages']+=repeated
        self.parts[15]=self.parts[5]
        with self.assertRaises(ValueError):verified_shift(self.old,self.fresh,self.parts)


if __name__=='__main__':unittest.main()
