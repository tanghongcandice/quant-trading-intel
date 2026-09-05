#!/usr/bin/env python3
"""Read-only X collector with a persistent, user-authorized browser profile.

The module globals are intentionally overrideable. quant-trading-intel's
scripts/xcrawl_project.py imports this module and replaces DATA_DIR,
EXPORT_DIR and DB_PATH before calling main().
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime as dt
import fcntl
import json
import math
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

try:
    from playwright.async_api import Page, async_playwright
except ImportError as exc:  # pragma: no cover - exercised by installation checks
    raise SystemExit(
        "x-crawler requires Playwright. Install it in the project environment "
        "with: python -m pip install playwright"
    ) from exc


SKILL_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("X_CRAWLER_DATA_DIR", SKILL_ROOT / "data"))
EXPORT_DIR = Path(os.environ.get("X_CRAWLER_EXPORT_DIR", DATA_DIR / "exports"))
DB_PATH = Path(os.environ.get("X_CRAWLER_DB_PATH", DATA_DIR / "accounts.db"))
CHROME_BIN = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

EXTRACT_TWEETS_JS = r"""
(articles) => articles.map((article) => {
  const abs = (href) => {
    try { return new URL(href, location.origin).href; } catch (_) { return href || ''; }
  };
  const metric = (testid) => {
    const node = article.querySelector(`[data-testid="${testid}"]`);
    if (!node) return null;
    const label = node.getAttribute('aria-label') || node.innerText || '';
    const match = String(label).match(/[\d,.]+\s*[KMB万亿]?/i);
    return match ? match[0].replace(/\s+/g, '') : null;
  };
  const time = article.querySelector('time[datetime]');
  let statusAnchor = time ? time.closest('a[href*="/status/"]') : null;
  if (!statusAnchor) {
    statusAnchor = Array.from(article.querySelectorAll('a[href*="/status/"]'))
      .find((a) => /\/[^/]+\/status\/\d+/.test(a.getAttribute('href') || '')) || null;
  }
  const href = statusAnchor ? statusAnchor.getAttribute('href') || '' : '';
  const match = href.match(/\/([^/?#]+)\/status\/(\d+)/);
  if (!match) return null;

  const username = decodeURIComponent(match[1]);
  const id = match[2];
  const textNode = article.querySelector('[data-testid="tweetText"]');
  const userNode = article.querySelector('[data-testid="User-Name"]');
  const userLines = userNode ? String(userNode.innerText || '').split('\n').map(x => x.trim()).filter(Boolean) : [];
  const handleLine = userLines.find(x => /^@/.test(x));
  const displayName = userLines.find(x => !/^@/.test(x) && x !== '·') || username;
  const social = article.querySelector('[data-testid="socialContext"]');
  const socialText = social ? String(social.innerText || '') : '';
  const replyText = String(article.innerText || '').slice(0, 500);

  const links = textNode ? Array.from(textNode.querySelectorAll('a[href]'))
    .map(a => abs(a.getAttribute('href'))).filter(Boolean) : [];
  const photos = Array.from(article.querySelectorAll('img[src*="pbs.twimg.com/media/"]'))
    .map(img => img.currentSrc || img.src || '')
    .filter(Boolean)
    .map(url => ({url, type: 'image'}));
  const statusLinks = Array.from(article.querySelectorAll('a[href*="/status/"]'))
    .map(a => a.getAttribute('href') || '')
    .map(h => h.match(/\/([^/?#]+)\/status\/(\d+)/))
    .filter(Boolean)
    .map(m => ({username: decodeURIComponent(m[1]), id: m[2]}));
  const quoted = statusLinks.find(x => x.id !== id) || null;

  return {
    id,
    id_str: id,
    url: abs(href),
    date: time ? time.getAttribute('datetime') : null,
    rawContent: textNode ? String(textNode.innerText || '').trim() : '',
    lang: textNode ? textNode.getAttribute('lang') : null,
    user: {
      username: (handleLine || `@${username}`).replace(/^@/, ''),
      displayname: displayName
    },
    links,
    media: {photos},
    replyCount: metric('reply'),
    retweetCount: metric('retweet'),
    likeCount: metric('like'),
    bookmarkCount: metric('bookmark'),
    viewCount: metric('app-text-transition-container'),
    isReply: /Replying to|正在回复|回复\s*@/i.test(replyText),
    retweetedTweet: /reposted|转发了/i.test(socialText) ? {socialContext: socialText} : null,
    quotedTweetId: quoted ? quoted.id : null
  };
}).filter(Boolean)
"""


def _truthy(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _profile_dir() -> Path:
    return Path(os.environ.get("X_CRAWLER_PROFILE_DIR", DATA_DIR / "browser_profile")).expanduser()


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _profile_dir().mkdir(parents=True, exist_ok=True)


def _ensure_db() -> sqlite3.Connection:
    _ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            profile_name TEXT PRIMARY KEY,
            profile_dir TEXT NOT NULL,
            signed_in_as TEXT,
            created_at TEXT NOT NULL,
            last_authenticated_at TEXT,
            last_verified_at TEXT
        )
        """
    )
    conn.commit()
    return conn


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _record_profile(*, authenticated: bool, signed_in_as: str | None = None) -> None:
    now = _now()
    with _ensure_db() as conn:
        conn.execute(
            """
            INSERT INTO accounts (
                profile_name, profile_dir, signed_in_as, created_at,
                last_authenticated_at, last_verified_at
            ) VALUES ('default', ?, ?, ?, ?, ?)
            ON CONFLICT(profile_name) DO UPDATE SET
                profile_dir=excluded.profile_dir,
                signed_in_as=COALESCE(excluded.signed_in_as, accounts.signed_in_as),
                last_authenticated_at=COALESCE(excluded.last_authenticated_at, accounts.last_authenticated_at),
                last_verified_at=excluded.last_verified_at
            """,
            (
                str(_profile_dir()),
                signed_in_as,
                now,
                now if authenticated else None,
                now,
            ),
        )
        conn.commit()


@contextlib.contextmanager
def _profile_lock():
    _ensure_dirs()
    lock_path = DATA_DIR / ".profile.lock"
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _launch_kwargs(*, headless: bool, proxy: str | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
        ],
        "viewport": {"width": 1440, "height": 1000},
    }
    if CHROME_BIN.exists():
        kwargs["executable_path"] = str(CHROME_BIN)
    if proxy:
        kwargs["proxy"] = {"server": proxy}
    return kwargs


async def _is_authenticated(page: Page) -> bool:
    selectors = (
        '[data-testid="SideNav_AccountSwitcher_Button"]',
        'a[data-testid="AppTabBar_Home_Link"]',
        'a[href="/compose/post"]',
    )
    for selector in selectors:
        try:
            if await page.locator(selector).count() > 0:
                return True
        except Exception:
            continue
    return False


async def _signed_in_as(page: Page) -> str | None:
    try:
        text = await page.locator('[data-testid="SideNav_AccountSwitcher_Button"]').inner_text(timeout=2000)
    except Exception:
        return None
    match = re.search(r"@([A-Za-z0-9_]{1,15})", text or "")
    return match.group(1) if match else None


async def _goto(page: Page, url: str) -> None:
    await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(2500)


async def _login(wait_seconds: int, proxy: str | None) -> int:
    with _profile_lock():
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(_profile_dir()), **_launch_kwargs(headless=False, proxy=proxy)
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await _goto(page, "https://x.com/home")
                if not await _is_authenticated(page):
                    print("请在打开的 X 页面完成登录；helper 不会读取或输出你的凭据。", flush=True)
                deadline = asyncio.get_running_loop().time() + max(wait_seconds, 1)
                while not await _is_authenticated(page):
                    if asyncio.get_running_loop().time() >= deadline:
                        _record_profile(authenticated=False)
                        print("X 登录等待超时；完成登录后重新运行 login。", file=sys.stderr)
                        return 2
                    await page.wait_for_timeout(1000)
                handle = await _signed_in_as(page)
                _record_profile(authenticated=True, signed_in_as=handle)
                print(json.dumps({"status": "authenticated", "account": handle}, ensure_ascii=False))
                return 0
            finally:
                await context.close()


async def _require_auth(page: Page) -> None:
    if await _is_authenticated(page):
        _record_profile(authenticated=True, signed_in_as=await _signed_in_as(page))
        return
    _record_profile(authenticated=False)
    raise RuntimeError(
        "X login/session unavailable. Run `python scripts/xcrawl.py login` "
        "and complete login in the dedicated browser profile."
    )


def _normalize_doc(doc: dict[str, Any]) -> dict[str, Any]:
    doc = dict(doc)
    user = dict(doc.get("user") or {})
    username = str(user.get("username") or "").lstrip("@")
    user["username"] = username
    doc["user"] = user
    doc["username"] = username
    doc["displayname"] = user.get("displayname")
    doc["content"] = doc.get("rawContent") or ""
    if doc.get("isReply"):
        doc["inReplyToTweetId"] = doc.get("inReplyToTweetId")
    return doc


async def _extract_visible(page: Page) -> list[dict[str, Any]]:
    articles = page.locator('article[data-testid="tweet"]')
    return [_normalize_doc(row) for row in await articles.evaluate_all(EXTRACT_TWEETS_JS)]


async def _collect_timeline(
    *,
    url: str,
    limit: int,
    target_username: str | None,
    requested_tweet_id: str | None,
    headless: bool,
    proxy: str | None,
    debug: bool,
) -> list[dict[str, Any]]:
    with _profile_lock():
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(_profile_dir()), **_launch_kwargs(headless=headless, proxy=proxy)
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await _goto(page, url)
                await _require_auth(page)
                try:
                    await page.locator('article[data-testid="tweet"]').first.wait_for(
                        state="visible", timeout=25_000
                    )
                except Exception as exc:
                    current = page.url.lower()
                    if any(token in current for token in ("/login", "/i/flow/", "account/access")):
                        raise RuntimeError("X redirected to a login or account checkpoint; run the login command") from exc
                    raise RuntimeError("X rendered no tweet cards; the page may be rate limited or unavailable") from exc

                found: dict[str, dict[str, Any]] = {}
                stable_rounds = 0
                max_rounds = max(3, min(30, math.ceil(max(limit, 1) / 6) * 2))
                for _ in range(max_rounds):
                    before = len(found)
                    for doc in await _extract_visible(page):
                        tweet_id = str(doc.get("id") or "")
                        actual = str(((doc.get("user") or {}).get("username") or "")).lower()
                        if not tweet_id:
                            continue
                        if target_username and actual != target_username.lower().lstrip("@"):
                            continue
                        if requested_tweet_id and tweet_id != requested_tweet_id:
                            continue
                        found[tweet_id] = doc
                    if len(found) >= limit or (requested_tweet_id and requested_tweet_id in found):
                        break
                    stable_rounds = stable_rounds + 1 if len(found) == before else 0
                    if stable_rounds >= 3:
                        break
                    await page.evaluate("window.scrollBy(0, Math.max(window.innerHeight * 2, 1400))")
                    await page.wait_for_timeout(int(os.environ.get("X_CRAWLER_SCROLL_DELAY_MS", "1800")))

                docs = list(found.values())
                docs.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
                if debug:
                    debug_path = EXPORT_DIR / "last-page.png"
                    await page.screenshot(path=str(debug_path), full_page=False)
                    print(json.dumps({"debug_screenshot": str(debug_path)}, ensure_ascii=False), file=sys.stderr)
                return docs[:limit]
            finally:
                await context.close()


def _write_output(docs: list[dict[str, Any]], output: Path, fmt: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "jsonl":
        text = "".join(json.dumps(doc, ensure_ascii=False) + "\n" for doc in docs)
    else:
        text = json.dumps(docs, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, delete=False) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    temp_path.replace(output)


async def _status(proxy: str | None) -> int:
    with _profile_lock():
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(_profile_dir()), **_launch_kwargs(headless=True, proxy=proxy)
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await _goto(page, "https://x.com/home")
                authenticated = await _is_authenticated(page)
                handle = await _signed_in_as(page) if authenticated else None
                _record_profile(authenticated=authenticated, signed_in_as=handle)
                print(json.dumps({"authenticated": authenticated, "account": handle}, ensure_ascii=False))
                return 0 if authenticated else 2
            finally:
                await context.close()


def _add_collection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--format", choices=("jsonl", "json"), default="jsonl")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proxy")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--headed", action="store_true")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect authorized X data as JSONL")
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="Open the dedicated profile for user login")
    login.add_argument("--wait-seconds", type=int, default=600)
    login.add_argument("--proxy")

    status = sub.add_parser("status", help="Check whether the dedicated profile is authenticated")
    status.add_argument("--proxy")

    user = sub.add_parser("user-tweets", help="Collect one user's timeline")
    user.add_argument("username")
    user.add_argument("--replies", action="store_true")
    _add_collection_args(user)

    search = sub.add_parser("search", help="Collect the live search timeline")
    search.add_argument("query")
    _add_collection_args(search)

    tweet = sub.add_parser("tweet", help="Collect one tweet by id or URL")
    tweet.add_argument("tweet_id")
    _add_collection_args(tweet)
    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.command == "login":
        return await _login(args.wait_seconds, args.proxy)
    if args.command == "status":
        return await _status(args.proxy)

    limit = max(1, min(int(args.limit), 200))
    target_username: str | None = None
    requested_tweet_id: str | None = None
    if args.command == "user-tweets":
        target_username = args.username.lstrip("@")
        suffix = "/with_replies" if args.replies else ""
        url = f"https://x.com/{target_username}{suffix}"
    elif args.command == "search":
        url = f"https://x.com/search?q={quote(args.query)}&src=typed_query&f=live"
    else:
        match = re.search(r"(?:status/)?(\d{8,})", args.tweet_id)
        if not match:
            raise RuntimeError("tweet expects a numeric tweet id or X status URL")
        requested_tweet_id = match.group(1)
        url = f"https://x.com/i/status/{requested_tweet_id}"
        limit = 1

    docs = await _collect_timeline(
        url=url,
        limit=limit,
        target_username=target_username,
        requested_tweet_id=requested_tweet_id,
        headless=not args.headed and _truthy("X_CRAWLER_HEADLESS", True),
        proxy=args.proxy,
        debug=args.debug,
    )
    _write_output(docs, args.output.expanduser(), args.format)
    print(json.dumps({"status": "success", "count": len(docs), "output": str(args.output.expanduser())}, ensure_ascii=False))
    return 0


def main() -> None:
    args = _parser().parse_args()
    try:
        raise SystemExit(asyncio.run(_run(args)))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as exc:
        print(f"x-crawler failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
