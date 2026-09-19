import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import substack_project


class FakePage:
    def __init__(self, results):
        self.results = list(results)
        self.endpoints = []
        self.waits = []

    def evaluate(self, _script, endpoint):
        self.endpoints.append(endpoint)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def wait_for_timeout(self, milliseconds):
        self.waits.append(milliseconds)


class PageJsonRequestTests(unittest.TestCase):
    def test_uses_page_context_and_parses_json(self):
        page = FakePage([{"ok": True, "status": 200, "body": json.dumps([{"id": 1}])}])

        result = substack_project.page_json_request(page, "/api/v1/archive?offset=0")

        self.assertEqual(result, [{"id": 1}])
        self.assertEqual(page.endpoints, ["/api/v1/archive?offset=0"])
        self.assertEqual(page.waits, [])

    def test_retries_transient_page_failure(self):
        page = FakePage(
            [
                RuntimeError("temporary network failure"),
                {"ok": True, "status": 200, "body": "[]"},
            ]
        )

        result = substack_project.page_json_request(page, "/api/v1/archive", retry_delay=0.25)

        self.assertEqual(result, [])
        self.assertEqual(page.waits, [250])
        self.assertEqual(len(page.endpoints), 2)

    def test_reports_failure_after_bounded_retries(self):
        page = FakePage(
            [
                {"ok": False, "status": 503, "body": "unavailable"},
                {"ok": False, "status": 503, "body": "unavailable"},
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "failed after 2 attempts"):
            substack_project.page_json_request(
                page, "/api/v1/archive", attempts=2, retry_delay=0
            )

        self.assertEqual(len(page.endpoints), 2)


if __name__ == "__main__":
    unittest.main()
