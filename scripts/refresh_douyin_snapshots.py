#!/usr/bin/env python3
"""Refresh authenticated Douyin profile snapshots with a persistent browser session."""
import argparse, asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright

PROFILES = {
    "douyin_jiujiujiucai": ("久韭究财", "https://www.douyin.com/user/MS4wLjABAAAAfZSJLO6q-2SWxDS2tp2oor3lawUH4JB2TPKWOGoykXU"),
    "douyin_panyiyoudianshen": ("潘姨有点神", "https://www.douyin.com/user/MS4wLjABAAAAiZFYelCAfbPcGXxkCEZEOpJPi-Fo_frPHiaEA45UerKIM-XTAXssDViEHNRu_bH2"),
}

EXTRACT = """
() => { const seen=new Set(), works=[];
 for (const link of Array.from(document.querySelectorAll('a[href^="/video/"]'))) {
  const m=String(link.getAttribute('href')||'').match(/\\/video\\/(\\d{15,})/); if(!m||seen.has(m[1])) continue; seen.add(m[1]);
  const card=String(link.innerText||link.getAttribute('aria-label')||'').trim();
  const ps=Array.from(link.querySelectorAll('p')).map(n=>String(n.innerText||'').trim()).filter(Boolean);
  const alt=link.querySelector('img[alt]')?.getAttribute('alt')||'';
  const title=ps.pop()||alt.replace(new RegExp('^'+__AUTHOR__+'：?'),'').trim()||card;
  const accessPattern=/(专属会员|会员专属|会员专享|会员内容|会员可见|付费作品|付费内容|订阅专享)/;
  const badge=Array.from(link.querySelectorAll('[class*="badge"],[class*="label"],[class*="tag"],[class*="vip"],[class*="member"],[data-e2e*="badge"],[aria-label]')).map(n=>String(n.innerText||n.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim()).filter(t=>t&&t.length<=40).join(' ');
  const match=badge.match(accessPattern), reviewOnly=Boolean(match);
  works.push({aweme_id:m[1],url:'https://www.douyin.com/video/'+m[1],author:__AUTHOR__,title,review_only:reviewOnly,access_label:reviewOnly?(match[1]||'付费内容'):null,pinned:card.includes('置顶'),_browser_session:true});
 } return works; }
"""

async def main(root: Path, profile_dir: Path, headless: bool, wait_seconds: int):
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(profile_dir), headless=headless, args=["--disable-blink-features=AutomationControlled"])
        try:
            for source, (author, url) in PROFILES.items():
                page = await context.new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    await page.reload(wait_until="domcontentloaded", timeout=60000)
                except Exception as exc:
                    # During first-time setup Douyin may redirect through a
                    # login/challenge page. Keep the headed browser alive so
                    # the user has time to complete it, then continue polling.
                    print(json.dumps({"source_id": source, "navigation_warning": str(exc)[:240]}, ensure_ascii=False), flush=True)
                await page.wait_for_timeout(5000)
                extractor = (root / 'scripts/douyin_profile_extract.js').read_text()
                works = await page.evaluate('(' + extractor + ')', {'authorName': author, 'profileUrl': url})
                waited = 0
                while not works and waited < wait_seconds:
                    await page.wait_for_timeout(5000); waited += 5
                    works = await page.evaluate('(' + extractor + ')', {'authorName': author, 'profileUrl': url})
                if not works: raise RuntimeError(f"{source}: no work cards rendered (login/session unavailable)")
                path=root/"data/browser_sessions"/(source+".jsonl"); path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps({"author":author,"works":works},ensure_ascii=False),encoding="utf-8")
                await page.close()
                print(json.dumps({"source_id":source,"count":len(works)},ensure_ascii=False), flush=True)
        finally: await context.close()

if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,required=True); ap.add_argument("--profile-dir",type=Path,required=True); ap.add_argument("--headed",action="store_true"); ap.add_argument("--wait-seconds",type=int,default=0); args=ap.parse_args()
    asyncio.run(main(args.root.resolve(),args.profile_dir.resolve(),not args.headed,args.wait_seconds))
