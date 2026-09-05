from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.ingestion_service import import_jsonl


def _default_scheduler_src(project_root: Path) -> Path:
    return project_root / "packages" / "ingestion_scheduler" / "src"


def _default_config(project_root: Path) -> Path:
    return project_root / "configs" / "ingestion" / "premarket.template.json"


def _extract_summary(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
    return {"stdout": text}


def run_collection(
    *,
    db_path: Path | None = None,
    config_path: Path | None = None,
    scheduler_src: Path | None = None,
    run_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    settings = get_settings(str(db_path) if db_path else None)
    config = (config_path or _default_config(settings.project_root)).resolve()
    scheduler = (scheduler_src or _default_scheduler_src(settings.project_root)).resolve()
    actual_run_id = run_id or None

    cmd = [
        sys.executable,
        "-m",
        "ingestion_scheduler",
        "run",
        "--config",
        str(config),
    ]
    if actual_run_id:
        cmd.extend(["--run-id", actual_run_id])
    if dry_run:
        cmd.append("--dry-run")

    completed = subprocess.run(
        cmd,
        cwd=str(settings.project_root),
        env={**os.environ, "PYTHONPATH": str(scheduler)},
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return {
            "status": "scheduler_failed",
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "db": str(settings.db_path),
            "config": str(config),
        }

    summary = _extract_summary(completed.stdout)
    items_path = Path(summary.get("items_path") or "")
    import_stats = None
    pending_review = []
    if not dry_run and items_path.exists():
        docs = [json.loads(line) for line in items_path.read_text().splitlines() if line.strip()]
        blocked_sources = set()
        for doc in docs:
            source = doc.get('source') or {}
            if source.get('type') != 'discord':
                continue
            text = (doc.get('content') or {}).get('text') or ''
            raw = doc.get('raw_payload') or {}
            translation = raw.get('translation') or {}
            if len(re.findall('[A-Za-z]', text)) >= 4 and not re.search('[\u4e00-\u9fff]', text) and not (translation.get('text') if isinstance(translation, dict) else translation):
                blocked_sources.add(source['id'])
        pending_review = [doc for doc in docs if (doc.get('source') or {}).get('id') in blocked_sources]
        if pending_review:
            pending_path = items_path.with_name('pending_codex_review.jsonl')
            pending_path.write_text(''.join(json.dumps(d, ensure_ascii=False) + '\n' for d in pending_review))
            ready_path = items_path.with_name('ready_to_import.jsonl')
            ready_path.write_text(''.join(json.dumps(d, ensure_ascii=False) + '\n' for d in docs if (d.get('source') or {}).get('id') not in blocked_sources))
            items_path = ready_path
        import_stats = import_jsonl(
            settings.db_path,
            items_path,
            run_id=summary.get("run_id"),
            mode="premarket_scheduler",
        )

    scheduler_status = summary.get("status") or "unknown"
    result_status = "success" if scheduler_status == "success" else scheduler_status
    if pending_review:
        result_status = 'awaiting_codex_review'
    if import_stats is not None and result_status != 'success':
        with sqlite3.connect(settings.db_path) as db:
            db.execute('UPDATE ingestion_runs SET status=?, summary_json=? WHERE id=?', (
                result_status, json.dumps({'import_stats':import_stats, 'scheduler_status':scheduler_status,
                    'pending_review_count':len(pending_review), 'pending_review_path':str(pending_path) if pending_review else None}),
                summary.get('run_id')))

    return {
        "status": result_status,
        "dry_run": dry_run,
        "db": str(settings.db_path),
        "config": str(config),
        "scheduler_summary": summary,
        "import_stats": import_stats,
        "pending_review_count": len(pending_review),
        "pending_review_path": str(pending_path) if pending_review else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run premarket collection and import emitted items into SQLite.")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--scheduler-src", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run_collection(
        db_path=args.db,
        config_path=args.config,
        scheduler_src=args.scheduler_src,
        run_id=args.run_id,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
