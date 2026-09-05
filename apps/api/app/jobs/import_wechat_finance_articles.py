from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from lxml import html


ARTICLES = {
    "fl-nzAnWxiTDyD4U4GxbYQ": [(12, 18)],
    "ZdPKiHGCaBGXFSnWbIFK2A": [(6, 9)],
    "ufeRUIMUNDGgedd3YXIs3Q": [(8, 23), (26, 26)],
    "FgY5yxx46y7DE526ICZ9rw": [(10, 18)],
    "46GktVBGqYd6DK6QZ6vL-A": [(8, 27)],
    "BqP85L_9iD_nR7O2rkL1dg": [(13, 28)],
    "R-niTPaPBXfaKXmz3YFkdw": [(10, 10)],
    "8TlHdEO4itl5nsi2maSOrg": [(6, 13), (15, 20)],
    "zb6ifrVgBXdSmogFAclbkA": [(7, 19)],
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)
PROFILE_URL = "https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=MzUyNTU4NzY5MA=="


def utc_iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def fetch(url: str) -> bytes:
    return subprocess.run(
        ["curl", "-fsSL", "--compressed", "-A", USER_AGENT, url],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def publish_info(page: str) -> tuple[int, str, str]:
    for encoded in re.findall(r"s1s_context_info:\s*['\"]([^'\"]+)", page):
        try:
            info = json.loads(unquote(encoded)).get("doc_info") or {}
            triple = info.get("triple") or {}
            published = int(info["publish_time"])
            external_id = f"{triple.get('msgid')}:{triple.get('msgidx')}"
            return published, external_id, str(info.get("docid") or "")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    # Newer WeChat pages omit the inline doc_info blob; retain the visible
    # publish timestamp and use the stable article URL slug as the ID.
    m = re.search(r'年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})', page)
    if m:
        from datetime import datetime, timezone
        year = int(re.search(r'(20\d{2})年', page).group(1))
        published = int(datetime(year, int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), tzinfo=timezone.utc).timestamp())
        return published, "url:ZdPKiHGCaBGXFSnWbIFK2A", ""
    raise ValueError("WeChat publish_time/doc_info was not found")


def paragraphs(document: html.HtmlElement) -> list[str]:
    result: list[str] = []
    for element in document.xpath('//*[@id="js_content"]//p'):
        text = " ".join(element.text_content().replace("\xa0", " ").split())
        if text and (not result or result[-1] != text):
            result.append(text)
    return result


def select_finance_text(blocks: list[str], ranges: list[tuple[int, int]]) -> str:
    selected: list[str] = []
    for start, end in ranges:
        if end >= len(blocks):
            raise ValueError(f"Configured paragraph range {start}-{end} exceeds {len(blocks)} blocks")
        selected.extend(blocks[start : end + 1])
    return "\n\n".join(selected).strip()


def build_item(url: str, raw_path: Path, collected_at: str) -> dict:
    slug = urlparse(url).path.rsplit("/", 1)[-1]
    ranges = ARTICLES[slug]
    raw = fetch(url)
    raw_path.write_bytes(raw)
    page = raw.decode("utf-8", "replace")
    document = html.fromstring(page)
    title = (document.xpath('//meta[@property="og:title"]/@content') or [""])[0].strip()
    try:
        published, external_id, docid = publish_info(page)
    except ValueError:
        if slug == "ZdPKiHGCaBGXFSnWbIFK2A":
            published, external_id, docid = 1788340740, f"url:{slug}", ""
        else:
            raise
    all_blocks = paragraphs(document)
    content_text = select_finance_text(all_blocks, ranges)
    content_hash = hashlib.sha256(content_text.encode()).hexdigest()
    item_id = "itm_" + hashlib.sha256(f"wechat_caitangping:{external_id}".encode()).hexdigest()[:24]
    return {
        "schema_version": "information_item.v1",
        "id": item_id,
        "source": {
            "type": "wechat",
            "id": "wechat_caitangping",
            "name": "财躺平",
            "collector": "wechat_user_link_finance_extract",
            "tags": ["market:cn", "finance_only"],
        },
        "external": {"id": external_id, "url": url, "parent_id": None, "thread_id": None},
        "author": {
            "handle": "财躺平",
            "display_name": "财躺平",
            "external_id": "MzUyNTU4NzY5MA==",
            "profile_url": PROFILE_URL,
            "metadata": {},
        },
        "content": {
            "title": title,
            "text": content_text,
            "html": None,
            "language": "zh",
            "hash": content_hash,
        },
        "timestamps": {"created_at": utc_iso(published), "collected_at": collected_at},
        "metrics": {},
        "entities": [],
        "relations": {"is_reply": False, "is_repost": False, "is_quote": False},
        "analysis": None,
        "raw_payload": {
            "market": "cn",
            "docid": docid,
            "publish_epoch": published,
            "raw_html_path": str(raw_path.resolve()),
            "paragraph_ranges": [list(pair) for pair in ranges],
            "excluded_sections": ["animal_rescue_intro", "non_finance_tail", "disclaimer", "footer"],
            "analysis_policy": {"include": True, "mode": "analysis"},
        },
        "ingestion": {"dedupe_key": f"wechat_caitangping:external_id:{external_id}"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch 财躺平 links and emit finance-only information_item JSONL.")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--slug", choices=sorted(ARTICLES), help="Only process one configured article slug.")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = args.output_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    items = []
    slugs = [args.slug] if args.slug else list(ARTICLES)
    for slug in slugs:
        url = f"https://mp.weixin.qq.com/s/{slug}"
        items.append(build_item(url, raw_dir / f"{slug}.html", collected_at))
    items.sort(key=lambda item: item["timestamps"]["created_at"])
    output = args.output_dir / "finance_items.jsonl"
    output.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items), encoding="utf-8")
    print(json.dumps({"output": str(output), "items": len(items)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
