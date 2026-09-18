from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "vendor" / "x-crawler" / "scripts" / "xcrawl.py"
SPEC = importlib.util.spec_from_file_location("xcrawl_long_post_test", HELPER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakePage:
    def __init__(self, batches: list[list[dict[str, Any]]]) -> None:
        self.batches = batches
        self.index = 0

    async def wait_for_timeout(self, _milliseconds: int) -> None:
        return None


async def fake_extract(page: FakePage) -> list[dict[str, Any]]:
    batch = page.batches[min(page.index, len(page.batches) - 1)]
    page.index += 1
    return batch


def test_detail_extraction_keeps_longest_rendering() -> None:
    preview = {"id": "123", "rawContent": "x" * 275}
    full = {"id": "123", "rawContent": "x" * 330}
    original = MODULE._extract_visible
    MODULE._extract_visible = fake_extract
    try:
        result = asyncio.run(MODULE._extract_requested_tweet(FakePage([[preview], [full], [full], [full]]), "123"))
    finally:
        MODULE._extract_visible = original
    assert result == full


def test_normalize_preserves_hydration_marker() -> None:
    doc = MODULE._normalize_doc(
        {
            "id": "123",
            "rawContent": "public long post",
            "detail_hydrated": True,
            "user": {"username": "author"},
        }
    )
    assert doc["content"] == "public long post"
    assert doc["detail_hydrated"] is True


def test_quoted_card_show_more_is_excluded() -> None:
    helper_source = HELPER.read_text(encoding="utf-8")
    assert "primaryTextContainer.querySelectorAll" in helper_source
    assert "!node.closest('div[role=\"link\"]')" in helper_source
    assert "explicitMore = /(?:Show more" not in helper_source


def test_closing_delimiter_can_end_a_complete_long_post() -> None:
    helper_source = HELPER.read_text(encoding="utf-8")
    assert "|[\\]）)'”」』])$" in helper_source


def test_detail_stable_unpunctuated_post_is_not_forced_pending() -> None:
    helper_source = HELPER.read_text(encoding="utf-8")
    assert "detail_hydration_reason: explicitMore ? 'explicit_more'" in helper_source
    assert 'hydrated.get("detail_hydration_reason") == "explicit_more"' in helper_source
    assert 'bool(hydrated.get("detail_hydration_candidate"))' not in helper_source


if __name__ == "__main__":
    test_detail_extraction_keeps_longest_rendering()
    test_normalize_preserves_hydration_marker()
    test_quoted_card_show_more_is_excluded()
    test_closing_delimiter_can_end_a_complete_long_post()
    test_detail_stable_unpunctuated_post_is_not_forced_pending()
    print("x crawler long-post tests passed")
