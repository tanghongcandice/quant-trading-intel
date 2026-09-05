#!/usr/bin/env python3
"""Preflight checks for authenticated fixtures and optional API credentials."""
from __future__ import annotations
import json, os, sys
from pathlib import Path

def main() -> int:
    root = Path(__file__).resolve().parents[1]
    cfg = root / "configs/ingestion/premarket.template.json"
    sources = json.loads(cfg.read_text(encoding="utf-8")).get("sources", [])
    ready = missing = 0
    for s in sources:
        if not s.get("enabled", True): continue
        fixture = s.get("fixture_file")
        browser_snapshot = s.get("browser_snapshot")
        if browser_snapshot:
            path = (root / browser_snapshot).resolve()
            if path.exists() and path.stat().st_size:
                ready += 1; print(f"ready source={s['id']} browser_snapshot={path}")
            else:
                missing += 1; print(f"waiting source={s['id']} browser_snapshot_missing={path}")
            continue
        if fixture:
            path = (root / fixture).resolve()
            if path.exists() and path.stat().st_size:
                ready += 1; print(f"ready source={s['id']} fixture={path}")
            else:
                missing += 1; print(f"waiting source={s['id']} missing_fixture={path}")
        elif s.get("type") == "discord" and s.get("mode") == "export":
            if os.environ.get("DISCORD_TOKEN"): ready += 1; print(f"ready source={s['id']} discord_token=set")
            else: missing += 1; print(f"waiting source={s['id']} DISCORD_TOKEN=unset")
        else:
            print(f"online source={s['id']} mode={s.get('mode','default')}")
    print(f"preflight_ready={ready} waiting={missing}")
    return 0

if __name__ == "__main__": raise SystemExit(main())
