from __future__ import annotations

import unittest

from app.jobs.repair_douyin_transcripts import (
    apply_contextual_corrections,
    review_a_share_terms,
)


class DouyinTermReviewTests(unittest.TestCase):
    def test_records_canonical_security_names_after_correction(self) -> None:
        corrected, changes = apply_contextual_corrections(
            "农业和光通信",
            "金剑米和天股通信都是中军，资金沉结还可以，美联储律决议也要关注。",
        )
        review = review_a_share_terms("农业和光通信", corrected, changes)
        self.assertEqual(review["status"], "passed")
        self.assertTrue(review["checked_before_ingestion"])
        self.assertIn("金健米业", review["canonical_terms"])
        self.assertIn("天孚通信", review["canonical_terms"])
        self.assertIn("中军", review["canonical_terms"])
        self.assertIn("承接", review["canonical_terms"])
        self.assertIn("利率决议", review["canonical_terms"])
        self.assertEqual(review["correction_count"], 4)

    def test_blocks_known_bad_term_if_correction_is_bypassed(self) -> None:
        with self.assertRaisesRegex(ValueError, "unresolved A-share ASR terms"):
            review_a_share_terms("农业", "龙头还是金剑米。")

    def test_allows_transcript_without_a_lexicon_match(self) -> None:
        review = review_a_share_terms("随聊", "今天先观察，不做判断。")
        self.assertEqual(review["canonical_terms"], [])


if __name__ == "__main__":
    unittest.main()
