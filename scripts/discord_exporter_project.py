#!/usr/bin/env python3
"""Export Discord channel messages through the project's signed-in browser profile.

The CLI intentionally follows the legacy discord-crawler exporter contract so
the scheduler keeps producing raw JSON artifacts before normalization.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "data" / "browser_profiles" / "discord"
STATE_DB = ROOT / "data" / "quant_intel.sqlite"
EXTRACTOR = ROOT / "scripts" / "discord_browser_extract.js"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(value.strip(), "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def cursor_cutoff(source_id: str | None, configured_after: str | None) -> datetime | None:
    candidates = [parse_datetime(configured_after)]
    if source_id and STATE_DB.exists():
        with sqlite3.connect(STATE_DB) as conn:
            row = conn.execute(
                "SELECT last_successful_created_at FROM source_cursors WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        if row and row[0]:
            parsed = parse_datetime(str(row[0]))
            if parsed:
                candidates.append(parsed - timedelta(hours=2))
    valid = [value for value in candidates if value is not None]
    return max(valid) if valid else None


def export_channel(args: argparse.Namespace) -> dict[str, Any]:
    cutoff = parse_datetime(args.after) if args.ignore_cursor else cursor_cutoff(args.source_id, args.after)
    url = f"https://discord.com/channels/{args.guild}/{args.channel}"
    extractor = EXTRACTOR.read_text(encoding="utf-8").strip()
    launch: dict[str, Any] = {
        "headless": not args.headed,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if CHROME.exists():
        launch["executable_path"] = str(CHROME)

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path = ROOT / 'data' / 'discord_checkpoints' / f'{args.channel}.json'
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    accumulated = {}
    if checkpoint_path.exists():
        saved = json.loads(checkpoint_path.read_text())
        if saved.get('cutoff') == str(cutoff) and saved.get('version') == 3:
            accumulated = {str(i['id']): i for i in saved.get('messages', [])}
    def save_checkpoint(rows):
        for row in rows:
            previous = accumulated.get(str(row['id'])) or {}
            if (row.get('author') or {}).get('name') == 'Unknown Discord author' and previous.get('author'):
                row['author'] = previous['author']
            accumulated[str(row['id'])] = row
        temporary = checkpoint_path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'version': 3, 'cutoff': str(cutoff), 'messages': list(accumulated.values())}, ensure_ascii=False))
        temporary.replace(checkpoint_path)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(str(PROFILE_DIR), **launch)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(4_000)
            if "/login" in page.url.lower() or page.locator('input[name="email"]').count():
                raise RuntimeError(
                    "Discord browser profile is signed out. Run this command once with --headed and sign in."
                )
            page.expose_function('discordCheckpoint', save_checkpoint)
            selector = '[role="article"][data-list-item-id^="chat-messages"]'
            result = {}
            for segment in range(12):
                if segment:
                    oldest_id = min(accumulated) if accumulated else None
                    page.goto(f'{url}/{oldest_id}' if oldest_id else url, wait_until='domcontentloaded', timeout=60000)
                for attempt in range(3):
                    try:
                        page.locator(selector).first.wait_for(state='visible', timeout=20000)
                        break
                    except Exception:
                        if attempt == 2:
                            raise RuntimeError('Discord message list did not render after 3 attempts; empty capture is not success')
                        page.reload(wait_until='domcontentloaded')
                result = page.evaluate(f'({extractor})', {
                    'guildId': str(args.guild), 'channelId': str(args.channel),
                    'cutoffIso': cutoff.isoformat() if cutoff else None,
                    'maxRounds': min(args.max_rounds, 100),
                    'anchorLatest': segment == 0, 'checkpoint': True,
                })
                if not result.get('items'):
                    raise RuntimeError('Discord returned no rendered messages; refusing success')
                if result.get('stop_reason') == 'cutoff_reached' or not cutoff:
                    break
            items = list(accumulated.values())
            # Discord occasionally renders a reply as "message unavailable"
            # in the timeline even though its deep link is accessible. Resolve
            # those parents in the same authenticated session before export.
            unresolved = []
            for item in items:
                reference = item.get("reference") or {}
                parent_id = reference.get("messageId")
                referenced = item.get("referencedMessage") or {}
                if parent_id and not str(referenced.get("content") or "").strip():
                    unresolved.append((item, str(parent_id)))
            resolver = context.new_page()
            try:
                for item, parent_id in unresolved[:30]:
                    resolver.goto(
                        f"https://discord.com/channels/{args.guild}/{args.channel}/{parent_id}",
                        wait_until="domcontentloaded",
                        timeout=60_000,
                    )
                    resolver.wait_for_timeout(1_500)
                    content_node = resolver.locator(f"#message-content-{parent_id}")
                    username_node = resolver.locator(f"#message-username-{parent_id}")
                    content = content_node.inner_text(timeout=3_000).strip() if content_node.count() else ""
                    author = username_node.inner_text(timeout=3_000).strip() if username_node.count() else ""
                    if content:
                        item["reference"]["unavailable"] = False
                        item["referencedMessage"] = {
                            "id": parent_id,
                            "content": content,
                            "author": {"displayName": author or "原消息作者", "name": author or "原消息作者"},
                        }
            finally:
                resolver.close()
        finally:
            context.close()

    if cutoff:
        dated = [parse_datetime(item.get("timestamp")) for item in items]
        oldest = min((value for value in dated if value), default=None)
        if oldest and oldest > cutoff and (result or {}).get("stop_reason") != "cutoff_reached":
            raise RuntimeError(
                "Discord export stopped before the required overlap cutoff "
                f"({oldest.isoformat()} > {cutoff.isoformat()}); increase --max-rounds"
            )
        items = [
            item
            for item in items
            if not parse_datetime(item.get("timestamp")) or parse_datetime(item.get("timestamp")) >= cutoff
        ]
    if args.before:
        before = parse_datetime(args.before)
        if before:
            items = [
                item
                for item in items
                if not parse_datetime(item.get("timestamp")) or parse_datetime(item.get("timestamp")) < before
            ]
    items.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=not args.reverse)
    payload = {
        "messages": items,
        "guild_id": str(args.guild),
        "channel_id": str(args.channel),
        "cutoff": cutoff.isoformat().replace("+00:00", "Z") if cutoff else None,
        "stop_reason": (result or {}).get("stop_reason"),
        "coverage_complete": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output": str(args.output), "count": len(items), "cutoff": payload["cutoff"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export")
    export.add_argument("--channel", required=True)
    export.add_argument("--guild", required=True)
    export.add_argument("--source-id")
    export.add_argument("--output", required=True, type=Path)
    export.add_argument("--format", default="Json", choices=["Json", "json"])
    export.add_argument("--after")
    export.add_argument('--ignore-cursor', action='store_true', help='Explicit historical backfill from --after')
    export.add_argument("--before")
    export.add_argument("--include-threads")
    export.add_argument("--reverse", action="store_true")
    export.add_argument("--max-rounds", type=int, default=600)
    export.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    lock_path = ROOT / 'data' / 'discord_profile.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = export_channel(args)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
