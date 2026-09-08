import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from chrome_preflight_diagnostics import record, validate


class ChromePreflightDiagnosticsTests(unittest.TestCase):
    def test_required_success_stages_gate_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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


if __name__ == "__main__":
    unittest.main()
