import unittest
from app.services.douyin_access_policy import excluded
from prepare_douyin_ingestion import _candidate_works

class PolicyTests(unittest.TestCase):
    def test_exact_exclusion_not_title_guess(self):
        self.assertTrue(excluded('douyin_jiujiujiucai','7686153728089015993'))
        self.assertFalse(excluded('douyin_jiujiujiucai','7686152973647700197'))
        self.assertFalse(excluded('another','7686153728089015993'))
    def test_user_removed_works_do_not_reenter_discovery(self):
        for sid,aid in [('douyin_jiujiujiucai','7696159959458023793'),
                        ('douyin_panyiyoudianshen','7692838219910468785')]:
            self.assertTrue(excluded(sid,aid))
            self.assertEqual(_candidate_works(sid,{}, {'works':[{'aweme_id':aid}]},None),[])
            self.assertFalse(excluded('another',aid))

    def test_discovery_excludes_before_download(self):
        self.assertEqual(_candidate_works('douyin_jiujiujiucai',{}, {'works':[{'aweme_id':'7686153728089015993'}]},None),[])

if __name__ == '__main__': unittest.main()
