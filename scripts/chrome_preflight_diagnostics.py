#!/usr/bin/env python3
"""Record auditable Chrome group-preflight diagnostics for scheduled runs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
REQUIRED_SUCCESS_STAGES = {
    "chrome_tab_enumeration",
    "group_dom_read",
    "processing_ledger_reuse",
    "group_receipt",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def run_dir(root: Path, run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("invalid run id")
    path = root / "runs" / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_event(path: Path, event: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def record(args: argparse.Namespace) -> dict[str, Any]:
    folder = run_dir(args.root, args.run_id)
    started_at = args.started_at or utc_now()
    ended_at = args.ended_at or utc_now()
    started = parse_time(started_at)
    ended = parse_time(ended_at)
    if ended < started:
        raise ValueError("ended-at precedes started-at")
    details = json.loads(args.details_json) if args.details_json else {}
    if not isinstance(details, dict):
        raise ValueError("details-json must decode to an object")
    event = {
        "run_id": args.run_id,
        "stage": args.stage,
        "attempt": args.attempt,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": round((ended - started).total_seconds() * 1000),
        "success": args.status == "success",
        "result_summary": args.summary,
        "details": details,
    }
    append_event(folder / "chrome_preflight_diagnostics.jsonl", event)
    return event


def begin(args: argparse.Namespace) -> dict[str, Any]:
    """Persist before a tool call, so even a timeout/reset leaves a start event."""
    folder = run_dir(args.root, args.run_id)
    token = uuid.uuid4().hex
    event = {'run_id': args.run_id, 'stage': args.stage, 'attempt': args.attempt,
             'token': token, 'started_at': utc_now(), 'monotonic': time.monotonic()}
    (folder / ('call_' + token + '.json')).write_text(json.dumps(event))
    append_event(folder / 'chrome_preflight_diagnostics.jsonl', {**event, 'event': 'start'})
    return event


def end(args: argparse.Namespace) -> dict[str, Any]:
    if not re.fullmatch(r'[a-f0-9]{32}', args.token):
        raise ValueError('Invalid call token')
    folder = run_dir(args.root, args.run_id)
    path = folder / ('call_' + args.token + '.json')
    event = json.loads(path.read_text())
    if event.get('ended_at'):
        raise ValueError('Call already ended')
    event.update(ended_at=utc_now(), duration_ms=max(1, round((time.monotonic()-event.pop('monotonic'))*1000)),
                 success=args.status == 'success', result_summary=args.summary,
                 details=json.loads(args.details_json or '{}'), event='end')
    path.write_text(json.dumps(event))
    append_event(folder / 'chrome_preflight_diagnostics.jsonl', event)
    return event


def power(args: argparse.Namespace) -> dict[str, Any]:
    folder = run_dir(args.root, args.run_id)
    started_at = utc_now()
    pmset = subprocess.run(["/usr/bin/pmset", "-g", "log"], text=True, capture_output=True)
    log_show = subprocess.run(
        [
            "/usr/bin/log", "show", "--style", "compact",
            "--start", args.window_start, "--end", args.window_end,
            "--predicate", 'process == "SkyComputerUseService"',
        ],
        text=True,
        capture_output=True,
    )
    window_start = datetime.fromisoformat(args.window_start)
    window_end = datetime.fromisoformat(args.window_end)

    def in_window(line: str) -> bool:
        try:
            stamp = datetime.strptime(line[:25], "%Y-%m-%d %H:%M:%S %z")
        except ValueError:
            return False
        if window_start.tzinfo is None:
            start = window_start.replace(tzinfo=stamp.tzinfo)
            end = window_end.replace(tzinfo=stamp.tzinfo)
        else:
            start, end = window_start, window_end
        return start <= stamp <= end

    display_lines = [
        line for line in pmset.stdout.splitlines()
        if "Display is turned" in line and in_window(line)
    ]
    service_lines = [line for line in log_show.stdout.splitlines() if "SkyComputerUseService" in line]
    (folder / "power_log.txt").write_text(pmset.stdout + pmset.stderr, encoding="utf-8")
    (folder / "skycomputeruse_log.txt").write_text(log_show.stdout + log_show.stderr, encoding="utf-8")
    ended_at = utc_now()
    event = {
        "run_id": args.run_id,
        "stage": "readonly_power_evidence",
        "attempt": 1,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": round((parse_time(ended_at) - parse_time(started_at)).total_seconds() * 1000),
        "success": pmset.returncode == 0 and log_show.returncode == 0,
        "result_summary": (
            f"display_transitions={len(display_lines)} "
            f"skycomputeruse_lines={len(service_lines)}; evidence only, not lock proof"
        ),
        "details": {
            "window_start": args.window_start,
            "window_end": args.window_end,
            "display_transitions": display_lines,
            "skycomputeruse_activity_count": len(service_lines),
            "interpretation_guard": (
                "Display-off, screenLock settings, and a single lock error do not prove historical session lock."
            ),
        },
    }
    append_event(folder / "chrome_preflight_diagnostics.jsonl", event)
    return event


def validate(args: argparse.Namespace) -> dict[str, Any]:
    folder = run_dir(args.root, args.run_id)
    path = folder / "chrome_preflight_diagnostics.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []
    # A later failed attempt invalidates an earlier success. An unclosed call is
    # a real incomplete operation, not a successful stage.
    latest = {row.get('stage'): row for row in rows if row.get('stage') in REQUIRED_SUCCESS_STAGES}
    succeeded = {stage for stage, row in latest.items() if row.get('success') is True and row.get('duration_ms', 0) > 0}
    missing = sorted(REQUIRED_SUCCESS_STAGES - succeeded)
    errors = []
    try:
        from group_capture_checkpoint import validate_capture
        capture = json.loads((folder / 'group_capture.json').read_text())
        coverage = validate_capture(capture, args.root, args.run_id, allow_partial=True)
        receipt = json.loads((folder / 'group_receipt.json').read_text())
        built = (folder / 'group_items.jsonl').read_bytes()
        if receipt.get('run_id') != args.run_id or receipt.get('sha256') != hashlib.sha256(built).hexdigest():
            raise ValueError('Receipt content hash/run mismatch')
        if receipt.get('capture_sha256') != hashlib.sha256((folder / 'group_capture.json').read_bytes()).hexdigest():
            raise ValueError('Capture content hash mismatch')
        if receipt.get('status') == 'partial_ready':
            # Hash-verified DOM windows prove the exported subset. Do not rewrite
            # failed full-coverage diagnostics as success to import that subset.
            missing = [stage for stage in missing if stage not in {'group_dom_read','processing_ledger_reuse','group_receipt'}]
        elif coverage['errors']:
            raise ValueError('Incomplete coverage cannot have a complete receipt')
    except (ValueError, OSError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    result = {"run_id": args.run_id, "ready": not missing and not errors,
              "missing_success_stages": missing, 'evidence_errors': errors}
    if result['ready']:
        result.update(capture_sha256=receipt['capture_sha256'], sha256=receipt['sha256'],
                      diagnostics_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (folder / "chrome_preflight_validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = result.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("--run-id", required=True)
    rec.add_argument("--stage", required=True)
    rec.add_argument("--attempt", type=int, default=1)
    rec.add_argument("--started-at")
    rec.add_argument("--ended-at")
    rec.add_argument("--status", choices=("success", "error"), required=True)
    rec.add_argument("--summary", required=True)
    rec.add_argument("--details-json")
    rec.set_defaults(handler=record)
    start = sub.add_parser('begin')
    start.add_argument('--run-id', required=True)
    start.add_argument('--stage', required=True)
    start.add_argument('--attempt', type=int, default=1)
    start.set_defaults(handler=begin)
    finish = sub.add_parser('end')
    finish.add_argument('--run-id', required=True)
    finish.add_argument('--token', required=True)
    finish.add_argument('--status', choices=('success', 'error'), required=True)
    finish.add_argument('--summary', required=True)
    finish.add_argument('--details-json', default='{}')
    finish.set_defaults(handler=end)
    pwr = sub.add_parser("power")
    pwr.add_argument("--run-id", required=True)
    pwr.add_argument("--window-start", required=True)
    pwr.add_argument("--window-end", required=True)
    pwr.set_defaults(handler=power)
    val = sub.add_parser("validate")
    val.add_argument("--run-id", required=True)
    val.set_defaults(handler=validate)
    return result


def main() -> None:
    args = parser().parse_args()
    result = args.handler(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == 'validate' and not result['ready']:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
