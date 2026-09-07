import unittest
from panyi_policy import gate,success,failure

class PolicyTests(unittest.TestCase):
    def test_disabled_local_interval_preserves_platform_wait(self):
        s={'local_interval_disabled':True,'next_allowed_at':99999,'interval_seconds':0}
        self.assertIsNone(gate(s,100))
        failure(s,'http_403',100)
        self.assertIsNone(gate(s,101))
        failure(s,'http_429',101,600)
        self.assertEqual(gate(s,102)['next_allowed_at'],701)
        for _ in range(8): success(s)
        self.assertEqual(s['interval_seconds'],0)
    def test_early_trigger_never_downloads(self):
        s={'next_allowed_at':1033}
        self.assertEqual(gate(s,1013)['status'],'wait_until_due')
        self.assertIsNone(gate(s,1033))
        self.assertEqual(gate(s,900)['status'],'cooldown')
    def test_success_floor_and_deadline(self):
        s={'interval_seconds':2400,'next_allowed_at':9999}
        for _ in range(16): success(s)
        self.assertEqual(s['interval_seconds'],1200)
        self.assertEqual(s['next_allowed_at'],9999)
    def test_failure_keeps_id_respects_retry_after(self):
        s={'current_id':'a','interval_seconds':1200}
        failure(s,'http_429',100,30000)
        self.assertEqual(s['current_id'],'a')
        self.assertEqual(s['next_allowed_at'],30100)
        self.assertEqual(s['success_streak'],0)
    def test_403_not_reported_as_frequency(self):
        s={}; failure(s,'http_403',100)
        self.assertEqual(s['last_failure']['reason'],'http_403')
        self.assertEqual(s['interval_seconds'],3600)
    def test_login_requires_user(self):
        s={}; failure(s,'login_required',100)
        self.assertEqual(gate(s,999999)['status'],'needs_attention')

if __name__=='__main__': unittest.main()
