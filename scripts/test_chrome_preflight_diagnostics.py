import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from chrome_preflight_diagnostics import record, validate, begin, end
from group_test_support import setup, ready
from prepare_douyin_group_run import prepare


class ChromePreflightDiagnosticsTests(unittest.TestCase):
    def test_required_success_stages_gate_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup(root); ready(root,'premarket_test'); prepare(root,'premarket_test')
            common = {
                "root": root,
                "run_id": "premarket_test",
                "attempt": 1,
                "started_at": "2026-09-08T08:00:00Z",
                "ended_at": "2026-09-08T08:00:01Z",
                "status": "success",
                "summary": "ok",
                "details_json": "{}",
            }
            for stage in ("chrome_tab_enumeration", "group_dom_read", "processing_ledger_reuse"):
                record(Namespace(stage=stage, **common))
            result = validate(Namespace(root=root, run_id="premarket_test"))
            self.assertFalse(result["ready"])
            self.assertEqual(result["missing_success_stages"], ["group_receipt"])
            record(Namespace(stage="group_receipt", **common))
            self.assertTrue(validate(Namespace(root=root, run_id="premarket_test"))["ready"])

    def test_error_attempt_does_not_satisfy_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = Namespace(
                root=root,
                run_id="premarket_test",
                stage="group_dom_read",
                attempt=1,
                started_at="2026-09-08T08:00:00Z",
                ended_at="2026-09-08T08:00:01Z",
                status="error",
                summary="tool error",
                details_json=json.dumps({"retry_after_seconds": 3}),
            )
            record(args)
            result = validate(Namespace(root=root, run_id="premarket_test"))
            self.assertIn("group_dom_read", result["missing_success_stages"])


    def test_interrupted_call_and_measured_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            args=Namespace(root=root,run_id='test',stage='group_dom_read',attempt=1)
            token=begin(args)['token']
            self.assertIn('group_dom_read',validate(Namespace(root=root,run_id='test'))['missing_success_stages'])
            done=end(Namespace(root=root,run_id='test',token=token,status='error',summary='timeout',details_json='{}'))
            self.assertGreater(done['duration_ms'],0)
            with self.assertRaises(ValueError):
                end(Namespace(root=root,run_id='test',token=token,status='success',summary='retry',details_json='{}'))

    def test_booleans_alone_and_later_failure_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            args=Namespace(root=root,run_id='test',attempt=1,started_at='2026-09-15T00:00:00Z',ended_at='2026-09-15T00:00:01Z',status='success',summary='ok',details_json='{}')
            for stage in ('chrome_tab_enumeration','group_dom_read','processing_ledger_reuse','group_receipt'):
                record(Namespace(stage=stage,**vars(args)))
            self.assertFalse(validate(Namespace(root=root,run_id='test'))['ready'])
            args.status='error'; args.attempt=2
            record(Namespace(stage='group_dom_read',**vars(args)))
            self.assertIn('group_dom_read',validate(Namespace(root=root,run_id='test'))['missing_success_stages'])

if __name__ == "__main__":
    unittest.main()
