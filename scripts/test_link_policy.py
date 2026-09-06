import unittest
from app.services.link_policy import is_link_only, suppress_link_translation


class LinkPolicyTests(unittest.TestCase):
    def test_url_only(self):
        item = {"content": {"text": "https://x.com/a?s=46"}, "raw_payload": {"translation": {"text": "bad"}}}
        self.assertTrue(is_link_only(item))
        suppress_link_translation(item)
        self.assertNotIn("translation", item["raw_payload"])
        self.assertFalse(item["raw_payload"]["translation_policy"]["required"])

    def test_comment_preserved(self):
        item = {"content": {"text": "Buy https://x.com/a"}, "raw_payload": {"translation": {"text": "买入 https://x.com/a"}}}
        self.assertFalse(is_link_only(item))
        suppress_link_translation(item)
        self.assertIn("translation", item["raw_payload"])

    def test_preview_uses_author_body(self):
        item = {"content": {"text": "https://youtu.be/a\nVideo title"}, "raw_payload": {"discord": {"content": "https://youtu.be/a"}}}
        self.assertTrue(is_link_only(item))


if __name__ == "__main__":
    unittest.main()
