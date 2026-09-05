#!/usr/bin/env python3
"""Download Substack posts through a persistent authenticated browser profile."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import timedelta
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "data" / "browser_profiles" / "substack"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
STATE_DB = ROOT / "data" / "premarket_state.sqlite"


def parsed(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            result = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-") or "post"


def effective_after(source_id: str | None, configured: str | None) -> datetime | None:
    values = [parsed(configured)]
    if source_id and STATE_DB.exists():
        with sqlite3.connect(STATE_DB) as conn:
            row = conn.execute(
                "SELECT last_successful_created_at FROM source_cursors WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        if row and row[0]:
            cursor = parsed(str(row[0]))
            if cursor:
                values.append(cursor - timedelta(hours=2))
    valid = [value for value in values if value]
    return max(valid) if valid else None


def archive_posts(page, publication: str, after: datetime | None, before: datetime | None) -> list[dict]:
    posts: list[dict] = []
    offset = 0
    while True:
        endpoint = f"{publication.rstrip('/')}/api/v1/archive?sort=new&search=&offset={offset}&limit=12"
        response = page.request.get(endpoint, headers={"Accept": "application/json"})
        if not response.ok:
            raise RuntimeError(f"Substack archive request failed: HTTP {response.status}")
        batch = response.json()
        if not isinstance(batch, list) or not batch:
            break
        posts.extend(batch)
        dates = [parsed(str(post.get("post_date") or "")) for post in batch]
        if after and any(value and value < after for value in dates):
            break
        offset += len(batch)
        if offset >= 240:
            break
    selected = []
    for post in posts:
        date = parsed(str(post.get("post_date") or ""))
        if after and date and date < after:
            continue
        if before and date and date >= before:
            continue
        selected.append(post)
    return selected


def article_text(page, post: dict) -> tuple[str, bool]:
    url = post.get("canonical_url")
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2_000)
    article = page.locator("article").first
    text = article.inner_text(timeout=10_000).strip() if article.count() else ""
    if not text:
        text = str(post.get("truncated_body_text") or post.get("description") or "").strip()
    audience = str(post.get("audience") or "")
    paywall = page.get_by_text(re.compile(r"subscribe to read|upgrade to paid|订阅后阅读", re.I)).count() > 0
    is_preview = audience == "only_paid" and paywall
    return text, is_preview


def download(args: argparse.Namespace) -> dict:
    publication = args.url.rstrip("/")
    after = effective_after(args.source_id, args.after)
    before = parsed(args.before)
    launch = {"headless": not args.headed, "args": ["--disable-blink-features=AutomationControlled"]}
    if CHROME.exists():
        launch["executable_path"] = str(CHROME)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)

    written = []
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(str(PROFILE_DIR), **launch)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(f"{publication}/archive", wait_until="domcontentloaded", timeout=60_000)
            posts = archive_posts(page, publication, after, before)
            for post in posts:
                text, is_preview = article_text(page, post)
                post_date = parsed(str(post.get("post_date") or ""))
                stamp = (post_date or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
                slug = safe_slug(str(post.get("slug") or post.get("id") or "post"))
                path = args.output / f"{stamp}_{slug}.md"
                metadata = {
                    "substack_id": post.get("id"),
                    "audience": post.get("audience"),
                    "is_preview": is_preview,
                    "post_date": post.get("post_date"),
                }
                body = "\n".join(
                    [
                        f"# {post.get('title') or slug}",
                        "",
                        f"original content: {post.get('canonical_url')}",
                        f"published: {post.get('post_date') or ''}",
                        f"metadata: {json.dumps(metadata, ensure_ascii=False, separators=(',', ':'))}",
                        "",
                        text,
                        "",
                    ]
                )
                path.write_text(body, encoding="utf-8")
                written.append(str(path))
        finally:
            context.close()
    return {"output": str(args.output), "count": len(written), "files": written}


def list_posts(args: argparse.Namespace) -> dict:
    clone = argparse.Namespace(**vars(args))
    clone.output = ROOT / "runs" / "substack_list"
    result = download(clone)
    for filename in result["files"]:
        text = Path(filename).read_text(encoding="utf-8")
        match = re.search(r"^original content:\s*(\S+)", text, re.M)
        if match:
            print(match.group(1))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["download", "list"])
    parser.add_argument("url")
    parser.add_argument("--source-id")
    parser.add_argument("--output", type=Path, default=ROOT / "runs" / "substack_download")
    parser.add_argument("--format", default="md")
    parser.add_argument("--after")
    parser.add_argument("--before")
    parser.add_argument("--rate")
    parser.add_argument("--proxy")
    parser.add_argument("--no-download-images", action="store_true")
    parser.add_argument("--download-files", action="store_true")
    parser.add_argument("--image-quality")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    result = download(args) if args.mode == "download" else list_posts(args)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
