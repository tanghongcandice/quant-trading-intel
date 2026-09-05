#!/usr/bin/env python3
"""Bridge rendered, authenticated browser captures into scheduler snapshots.

The browser-side extractor POSTs JSON to this process.  No cookies, tokens, or
browser storage are accepted or persisted; only the explicitly captured public
DOM records are written.  Files are replaced atomically so the scheduler never
sees a partial snapshot.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


SOURCES = {
    "x_haochihaochiaaa": ("x", "x_haochihaochiaaa.json"),
    "x_aleabitoreddit": ("x", "x_aleabitoreddit.json"),
    "x_edgerunner17888": ("x", "x_edgerunner17888.json"),
    "discord_tianyi_edgerunner_trades": ("discord", "discord_tianyi_edgerunner_trades.json"),
    "discord_haochi_daqu": ("discord", "discord_haochi_daqu.json"),
    "discord_club500_edgerunner_messages": ("discord", "discord_club500_edgerunner_messages.json"),
    "discord_club500_fm_trade_chat": ("discord", "discord_club500_fm_trade_chat.json"),
    "douyin_jiujiujiucai": ("douyin", "douyin_jiujiujiucai.jsonl"),
    "douyin_panyiyoudianshen": ("douyin", "douyin_panyiyoudianshen.jsonl"),
}


def _validate(source_id: str, payload: Any) -> Any:
    if source_id not in SOURCES:
        raise ValueError(f"unknown source_id: {source_id}")
    kind, _ = SOURCES[source_id]
    if kind == "discord":
        if isinstance(payload, list):
            payload = {"messages": payload}
        if not isinstance(payload, dict):
            raise ValueError("Discord capture must be an object with a messages/items list")
        # The current browser extractor emits `items`; retain that envelope
        # and also accept the legacy `messages` name.
        if not isinstance(payload.get("messages") or payload.get("items"), list):
            raise ValueError("Discord capture must be an object with a messages/items list")
    elif kind == "douyin":
        if isinstance(payload, list):
            payload = {"works": payload}
        if not isinstance(payload, dict) or not isinstance(payload.get("works"), list):
            raise ValueError("Douyin capture must be an object with a works list")
    else:
        if isinstance(payload, dict):
            payload = payload.get("items", [])
        if not isinstance(payload, list):
            raise ValueError("X capture must be a tweet array")
    return payload


def _write_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in payload) + "\n" if isinstance(payload, list) and path.suffix == ".jsonl" else json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Handler(BaseHTTPRequestHandler):
    root: Path

    def do_POST(self) -> None:  # noqa: N802
        source_id = urlparse(self.path).path.removeprefix("/capture/").strip("/")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = _validate(source_id, json.loads(self.rfile.read(length)))
            path = self.root / "data" / "browser_sessions" / SOURCES[source_id][1]
            _write_atomic(path, payload)
            body = json.dumps({"ok": True, "source_id": source_id, "path": str(path), "count": len(payload if isinstance(payload, list) else payload.get("messages", payload.get("items", payload.get("works", []))))}, ensure_ascii=False).encode()
            self.send_response(200)
        except Exception as exc:  # noqa: BLE001
            body = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode()
            self.send_response(400)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        """Small GET fallback for browser sandboxes that disallow fetch/POST."""
        parsed = urlparse(self.path)
        source_id = parsed.path.removeprefix("/capture/").strip("/")
        try:
            raw = parse_qs(parsed.query).get("data", [None])[0]
            if raw is None:
                raise ValueError("missing data query parameter")
            payload = _validate(source_id, json.loads(unquote(raw)))
            path = self.root / "data" / "browser_sessions" / SOURCES[source_id][1]
            _write_atomic(path, payload)
            body = json.dumps({"ok": True, "source_id": source_id, "path": str(path)}, ensure_ascii=False).encode()
            self.send_response(200)
        except Exception as exc:  # noqa: BLE001
            body = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode()
            self.send_response(400)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    Handler.root = args.root.resolve()
    print(json.dumps({"listening": f"http://{args.host}:{args.port}", "sources": sorted(SOURCES)}, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
