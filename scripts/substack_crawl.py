#!/usr/bin/env python3
"""Small dependency-free Substack RSS crawler used by ingestion_scheduler."""
from __future__ import annotations

import argparse
import datetime as dt
import html
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}: self.skip += 1
        elif tag in {"p", "div", "br", "li", "h1", "h2", "h3"}: self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.skip: self.skip -= 1
        elif tag in {"p", "div", "li", "h1", "h2", "h3"}: self.parts.append("\n")
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)


def clean(content: str) -> str:
    p = TextExtractor(); p.feed(html.unescape(content))
    text = re.sub(r"\n[ \t]+", "\n", "".join(p.parts))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_date(value: str) -> dt.datetime | None:
    try: return dt.datetime.strptime(value[:25], "%a, %d %b %Y %H:%M:%S %z")
    except Exception: return None


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("mode", choices=["download", "list"]); ap.add_argument("url")
    ap.add_argument("--output", type=Path); ap.add_argument("--after"); ap.add_argument("--before"); ap.add_argument("--format", default="md")
    ap.add_argument("--no-download-images", action="store_true"); ap.add_argument("--rate"); ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(); feed_url = a.url.rstrip("/") + "/feed"
    req = urllib.request.Request(feed_url, headers={"User-Agent": "quant-trading-intel/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r: root = ET.fromstring(r.read())
    ns = {"c": "http://purl.org/rss/1.0/modules/content/"}; rows=[]
    for item in root.findall(".//item"):
        link=(item.findtext("link") or "").strip(); title=(item.findtext("title") or "").strip(); pub=item.findtext("pubDate") or ""; d=parse_date(pub)
        if a.after and d and d.date() < dt.date.fromisoformat(a.after): continue
        if a.before and d and d.date() > dt.date.fromisoformat(a.before): continue
        rows.append((d, title, link, item.findtext("c:encoded", namespaces=ns) or item.findtext("description") or ""))
    if a.mode == "list":
        for _, _, link, _ in rows: print(link)
        return 0
    out=a.output; out.mkdir(parents=True, exist_ok=True)
    for d,title,link,body in rows:
        slug=re.sub(r"[^A-Za-z0-9_-]+", "-", title).strip("-")[:100] or "post"
        date=(d.date().isoformat() if d else "unknown")
        text=f"# {title}\n\nSource: {link}\n\nDate: {date}\n\n{clean(body)}\n"
        (out/f"{date}_{slug}.md").write_text(text, encoding="utf-8")
    if a.verbose: print(f"downloaded {len(rows)} posts", file=sys.stderr)
    return 0
if __name__ == "__main__": raise SystemExit(main())
