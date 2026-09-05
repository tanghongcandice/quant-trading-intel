#!/usr/bin/env python3
"""Legacy/manual repair utility for Discord and Substack browser snapshots.

The scheduled pipeline no longer reads these snapshots: X, Discord, and
Substack all invoke live command-line collectors. Keep this script only for
manual DOM diagnostics and historical snapshot repair.
"""
import argparse, asyncio, json, re
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
CHROME_BIN = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
JOBS = [
 ("discord_tianyi_edgerunner_trades", "discord", "https://discord.com/channels/1369047294560698450/1372032779050684616", "discord_browser_extract.js", {"guildId":"1369047294560698450","channelId":"1372032779050684616"}),
 ("discord_haochi_daqu", "discord", "https://discord.com/channels/1409416284621508620/1461938466840379463", "discord_browser_extract.js", {"guildId":"1409416284621508620","channelId":"1461938466840379463"}),
 ("discord_club500_edgerunner_messages", "discord", "https://discord.com/channels/1466161319433601179/1466187555262173436", "discord_browser_extract.js", {"guildId":"1466161319433601179","channelId":"1466187555262173436"}),
 ("discord_club500_fm_trade_chat", "discord", "https://discord.com/channels/1466161319433601179/1466163632751644753", "discord_browser_extract.js", {"guildId":"1466161319433601179","channelId":"1466163632751644753"}),
 ("substack_edgerunner17888", "substack", "https://edgerunner17888.substack.com/archive", "substack_browser_extract.js", {}),
]

async def main(root: Path, profiles: Path, headed: bool, wait_seconds: int, initial_wait: int):
    async with async_playwright() as p:
        for sid, kind, url, jsfile, args in JOBS:
            profile = profiles / kind
            launch_kwargs = {
                "headless": not headed,
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            # Use the installed stable Chrome for OAuth pages (Google blocks the
            # Playwright-bundled Chromium as an unsupported browser).
            if CHROME_BIN.exists():
                launch_kwargs["executable_path"] = str(CHROME_BIN)
            ctx = await p.chromium.launch_persistent_context(str(profile), **launch_kwargs)
            try:
                page = await ctx.new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    await page.wait_for_timeout(3000)
                except Exception as exc:
                    print(json.dumps({"source_id": sid, "warning": f"navigation failed: {exc}"}, ensure_ascii=False), flush=True)

                # Never treat a login page (or its shell) as a successful extraction.
                # In headed setup mode, leave the page open while the user signs in.
                deadline = 0.0
                while True:
                    current_url = page.url.lower()
                    try:
                        body = (await page.locator("body").inner_text(timeout=3000)).lower()
                    except Exception:
                        body = ""
                    url_login = any(marker in current_url for marker in ("/login", "/i/flow/login", "signin"))
                    try:
                        login_button = await page.get_by_role(
                            "button", name=re.compile(r"^(log in|sign in|登录|登入)$", re.I)
                        ).count()
                        login_link = await page.get_by_role(
                            "link", name=re.compile(r"^(log in|sign in|登录|登入)$", re.I)
                        ).count()
                    except Exception:
                        login_button = 0
                        login_link = 0
                    # X often renders a public profile and appends a login dialog;
                    # the URL itself does not contain /login in that case.
                    try:
                        x_login_prompt = await page.get_by_text(
                            re.compile(r"^log in or sign up for x$", re.I)
                        ).count()
                    except Exception:
                        x_login_prompt = 0
                    on_login = url_login or login_button > 0 or login_link > 0 or x_login_prompt > 0
                    if not on_login:
                        break
                    if not headed:
                        break
                    if deadline == 0.0:
                        deadline = asyncio.get_running_loop().time() + initial_wait
                        print(json.dumps({"source_id": sid, "status": "waiting_for_login", "seconds": initial_wait}, ensure_ascii=False), flush=True)
                    if asyncio.get_running_loop().time() >= deadline:
                        break
                    await page.wait_for_timeout(2000)

                if on_login:
                    raise RuntimeError("login/session unavailable; browser stayed on the login page")

                # Give the authenticated page a short settle period before extraction.
                await page.wait_for_timeout(2000)
                source = (root / "scripts" / jsfile).read_text(encoding="utf-8").strip()
                # Substack archive pages contain links/cards rather than article
                # body markup. Resolve the newest post link in the authenticated
                # session before running the DOM extractor.
                if kind == "substack":
                    href = await page.locator('a[href*="/p/"]').first.get_attribute("href")
                    if href:
                        from urllib.parse import urljoin
                        await page.goto(urljoin(page.url, href), wait_until="domcontentloaded", timeout=60000)
                        await page.wait_for_timeout(3000)
                result = await page.evaluate(f"({source})", args)
                def usable(value):
                    if not value:
                        return False
                    if kind == "substack" and isinstance(value, dict):
                        # A public shell can return a title with no article body;
                        # that is not a valid authenticated snapshot.
                        return bool((value.get("content_html") or "").strip())
                    return True
                waited = 0
                while not usable(result) and headed and waited < wait_seconds:
                    await page.wait_for_timeout(5000); waited += 5
                    result = await page.evaluate(f"({source})", args)
                if not usable(result):
                    raise RuntimeError("no rendered records; login/session unavailable or page still loading")
                path = root / "data/browser_sessions" / (sid + (".jsonl" if kind == "douyin" else ".json")); path.parent.mkdir(parents=True, exist_ok=True)
                payload = result if kind in {"x","discord"} else result
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps({"source_id":sid,"count":len(result) if isinstance(result,list) else 1},ensure_ascii=False), flush=True)
                await page.close()
            finally: await ctx.close()

if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,default=ROOT); ap.add_argument("--profiles",type=Path,default=None); ap.add_argument("--headed",action="store_true"); ap.add_argument("--wait-seconds",type=int,default=0); ap.add_argument("--initial-wait-seconds",type=int,default=0); a=ap.parse_args()
    asyncio.run(main(a.root.resolve(), (a.profiles or (a.root/"data/browser_profiles")).resolve(), a.headed, a.wait_seconds, a.initial_wait_seconds))
