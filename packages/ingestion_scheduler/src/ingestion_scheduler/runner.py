from __future__ import annotations

import time
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .adapters.base import AdapterContext
from .registry import ADAPTERS, adapter_for
from .state import StateStore
from .utils import (
    append_jsonl,
    atomic_write_json,
    canonical_json,
    ensure_dir,
    read_json,
    resolve_path,
    run_id_now,
    sha256_text,
    utc_now_iso,
)


def load_config(config_path: Path) -> dict[str, Any]:
    config = read_json(config_path)
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    if config.get("version") != 1:
        raise ValueError("Config version must be 1.")
    sources = config.get("sources")
    if not isinstance(sources, list):
        raise ValueError("Config must contain a sources list.")
    seen: set[str] = set()
    for source in sources:
        source_id = source.get("id")
        source_type = source.get("type")
        if not source_id or not isinstance(source_id, str):
            raise ValueError("Every source needs a string id.")
        if source_id in seen:
            raise ValueError(f"Duplicate source id: {source_id}")
        seen.add(source_id)
        if source_type not in ADAPTERS:
            raise ValueError(f"Unknown source type for {source_id}: {source_type}")


def config_base_dir(config: dict[str, Any], config_path: Path) -> Path:
    defaults = config.get("defaults", {})
    base_value = config.get("base_dir") or defaults.get("base_dir") or "."
    return resolve_path(base_value, config_path.parent)


def _cursor_eligible(item: dict[str, Any], source: dict[str, Any]) -> bool:
    """Exclude Discord context-only authors from successful watermarks."""
    if source.get("type") != "discord":
        return True
    targets = [str(value).strip().casefold() for value in source.get("target_authors") or [] if str(value).strip()]
    if not targets:
        return True
    author = item.get("author") or {}
    raw_author = ((item.get("raw_payload") or {}).get("discord") or {}).get("author") or {}
    values = [
        author.get("handle"), author.get("display_name"),
        raw_author.get("name"), raw_author.get("displayName"),
    ]
    normalized = [str(value).strip().casefold() for value in values if str(value or "").strip()]
    return any(target in value for target in targets for value in normalized)


def _advance_main_cursor(db_path: Path, source_id: str, item: dict[str, Any], run_id: str) -> None:
    """Mirror successful collection coverage into the final-store cursor."""
    created = str((item.get("timestamps") or {}).get("created_at") or "")
    if not created or not db_path.exists():
        return
    external_id = (item.get("external") or {}).get("id")
    with sqlite3.connect(db_path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS source_cursors (
            source_id TEXT PRIMARY KEY,
            last_successful_created_at TEXT,
            last_successful_external_id TEXT,
            updated_at TEXT NOT NULL,
            run_id TEXT NOT NULL
        )""")
        current = conn.execute(
            "SELECT last_successful_created_at FROM source_cursors WHERE source_id = ?", (source_id,)
        ).fetchone()
        if current and (current[0] or "") >= created:
            return
        conn.execute(
            """INSERT INTO source_cursors(source_id,last_successful_created_at,last_successful_external_id,updated_at,run_id)
               VALUES(?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET
               last_successful_created_at=excluded.last_successful_created_at,
               last_successful_external_id=excluded.last_successful_external_id,
               updated_at=excluded.updated_at, run_id=excluded.run_id""",
            (source_id, created, external_id, utc_now_iso(), run_id),
        )


def _final_store_contains(db_path: Path, source_id: str, external_id: str | None) -> bool:
    """Treat the final information store as the authoritative dedupe ledger."""
    if not external_id or not db_path.exists():
        return False
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM information_items WHERE source_id = ? AND external_id = ? LIMIT 1",
                (source_id, str(external_id)),
            ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


def _final_store_cursor(db_path: Path, source_id: str) -> dict[str, Any] | None:
    """Read only a cursor committed by the final-store import transaction."""
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM source_cursors WHERE source_id = ?", (source_id,)).fetchone()
    except sqlite3.Error:
        return None
    return dict(row) if row else None


def select_sources(
    config: dict[str, Any],
    *,
    only: list[str] | None = None,
    include_disabled: bool = False,
) -> list[dict[str, Any]]:
    only_set = set(only or [])
    selected = []
    for source in config.get("sources", []):
        if only_set and source["id"] not in only_set:
            continue
        if not include_disabled and source.get("enabled", True) is False:
            continue
        selected.append(source)
    return selected


def run_scheduler(
    *,
    config_path: Path,
    run_id: str | None = None,
    only: list[str] | None = None,
    include_disabled: bool = False,
    include_duplicates: bool = False,
    dry_run: bool = False,
    fail_fast: bool = False,
) -> dict[str, Any]:
    config = load_config(config_path)
    defaults = config.get("defaults", {})
    base_dir = config_base_dir(config, config_path)
    state_db = resolve_path(defaults.get("state_db", "data/ingestion_state.sqlite"), base_dir)
    output_dir = resolve_path(defaults.get("output_dir", "runs"), base_dir)
    timeout_seconds = int(defaults.get("timeout_seconds", 600))
    max_retries = int(defaults.get("max_retries", 1))
    retry_backoff_seconds = float(defaults.get("retry_backoff_seconds", 5))

    run_id = run_id or run_id_now()
    run_dir = ensure_dir(output_dir / run_id)
    raw_dir = ensure_dir(run_dir / "raw")
    items_path = run_dir / "items.jsonl"
    errors_path = run_dir / "errors.jsonl"
    summary_path = run_dir / "run_summary.json"
    collected_at = utc_now_iso()
    final_db = base_dir / "data" / "quant_intel.sqlite"

    state = StateStore(state_db)
    state.start_run(run_id, config_path)
    sources = select_sources(config, only=only, include_disabled=include_disabled)
    summary: dict[str, Any] = {
        "run_id": run_id,
        "dry_run": dry_run,
        "started_at": collected_at,
        "config_path": str(config_path),
        "state_db": str(state_db),
        "run_dir": str(run_dir),
        "items_path": str(items_path),
        "errors_path": str(errors_path),
        "source_count": len(sources),
        "sources": [],
        "totals": {"items": 0, "new": 0, "duplicates": 0, "failed_sources": 0},
    }

    interrupted = False
    try:
        for source in sources:
            source_summary = _run_source(
                source=source,
                context=AdapterContext(
                    base_dir=base_dir,
                    run_id=run_id,
                    run_dir=run_dir,
                    raw_dir=raw_dir,
                    collected_at=collected_at,
                    dry_run=dry_run,
                    timeout_seconds=int(source.get("timeout_seconds", timeout_seconds)),
                    processed_item=lambda source_id, external_id: (
                        state.get_processed_item(source_id, external_id)
                        if _final_store_contains(final_db, source_id, external_id)
                        else None
                    ),
                ),
                state=state,
                max_retries=int(source.get("max_retries", max_retries)),
                retry_backoff_seconds=float(source.get("retry_backoff_seconds", retry_backoff_seconds)),
                include_duplicates=include_duplicates,
                dry_run=dry_run,
                items_path=items_path,
                errors_path=errors_path,
            )
            summary["sources"].append(source_summary)
            summary["totals"]["items"] += source_summary.get("item_count", 0)
            summary["totals"]["new"] += source_summary.get("new_count", 0)
            summary["totals"]["duplicates"] += source_summary.get("duplicate_count", 0)
            if source_summary["status"] != "success":
                summary["totals"]["failed_sources"] += 1
                if fail_fast:
                    break
    except BaseException:
        interrupted = True
        raise
    finally:
        status = "interrupted" if interrupted else ("success" if summary["totals"]["failed_sources"] == 0 else "partial_failure")
        summary["finished_at"] = utc_now_iso()
        summary["status"] = status
        atomic_write_json(summary_path, summary)
        state.finish_run(run_id, status, summary)
        state.close()

    return summary


def _run_source(
    *,
    source: dict[str, Any],
    context: AdapterContext,
    state: StateStore,
    max_retries: int,
    retry_backoff_seconds: float,
    include_duplicates: bool,
    dry_run: bool,
    items_path: Path,
    errors_path: Path,
) -> dict[str, Any]:
    source_id = source["id"]
    source_type = source["type"]
    source_raw_dir = context.raw_dir / source_id
    config_hash = sha256_text(canonical_json(source))
    attempts = max_retries + 1
    last_error: str | None = None

    for attempt in range(1, attempts + 1):
        state.start_source(
            run_id=context.run_id,
            source_id=source_id,
            source_type=source_type,
            attempt=attempt,
            config_hash=config_hash,
            raw_dir=source_raw_dir,
        )
        try:
            # Browser snapshots must be refreshed before every collection.
            # Refuse stale captures instead of reporting a misleading
            # "no new items" result from an old file.
            snapshot_ref = source.get("browser_snapshot") or (
                source.get("fixture_file") if source.get("mode") == "browser_session" else None
            )
            if snapshot_ref and not dry_run:
                snapshot_path = resolve_path(str(snapshot_ref), context.base_dir)
                max_age_hours = float(source.get("max_snapshot_age_hours", 6))
                age_hours = (time.time() - snapshot_path.stat().st_mtime) / 3600 if snapshot_path.exists() else max_age_hours + 1
                if age_hours > max_age_hours:
                    raise RuntimeError(
                        f"stale browser snapshot ({age_hours:.1f}h old; limit {max_age_hours:.1f}h): {snapshot_path}. "
                        "Refresh the browser page and capture a new snapshot before running ingestion."
                    )
            adapter = adapter_for(source_type)
            result = adapter.collect(source, context)
            seen_at = utc_now_iso()
            new_count = 0
            duplicate_count = 0
            emitted_docs: list[dict[str, Any]] = []

            # Apply the independent successful watermark with a small overlap
            # window.  The complete browser snapshot remains in artifacts;
            # this only controls which records are candidates for this run.
            # Scheduler state is a capture/audit ledger. Only the cursor
            # committed by final-store import may exclude candidate records.
            final_db = context.base_dir / "data" / "quant_intel.sqlite"
            cursor = _final_store_cursor(final_db, source_id)
            cutoff = None
            if cursor and cursor.get("last_successful_created_at"):
                try:
                    cutoff = datetime.fromisoformat(str(cursor["last_successful_created_at"]).replace("Z", "+00:00")) - timedelta(hours=2)
                except ValueError:
                    cutoff = None
            candidate_items = result.items
            if cutoff is not None:
                candidate_items = []
                for doc in result.items:
                    raw = ((doc.get("timestamps") or {}).get("created_at"))
                    try:
                        created = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                    except (TypeError, ValueError):
                        # Keep undated records; dedupe protects against repeats.
                        candidate_items.append(doc)
                        continue
                    try:
                        if created >= cutoff:
                            candidate_items.append(doc)
                    except TypeError:
                        # A timezone-less legacy timestamp is retained and
                        # handled by external-id/content dedupe.
                        candidate_items.append(doc)

            if not dry_run:
                for item in candidate_items:
                    duplicate_of = state.find_content_duplicate(
                        item, [str(value) for value in source.get("dedupe_against_sources") or []]
                    )
                    if duplicate_of:
                        duplicate_count += 1
                        append_jsonl(
                            context.run_dir / "cross_source_dedupe_audit.jsonl",
                            [{
                                "source_id": source_id,
                                "external_id": (item.get("external") or {}).get("id"),
                                "duplicate_of": duplicate_of,
                                "seen_at": seen_at,
                            }],
                        )
                        continue
                    external_id = (item.get("external") or {}).get("id")
                    committed = _final_store_contains(final_db, source_id, external_id)
                    inserted, item_id = state.upsert_item(item, context.run_id, seen_at)
                    recoverable = not inserted and not committed
                    item["id"] = item_id
                    item.setdefault("ingestion", {})
                    item["ingestion"].update(
                        {
                            "run_id": context.run_id,
                            "source_id": source_id,
                            "seen_at": seen_at,
                            "is_new": inserted or recoverable,
                            "recovered_from_uncommitted_state": recoverable,
                        }
                    )
                    if inserted or recoverable:
                        new_count += 1
                    else:
                        duplicate_count += 1
                    # A state-only item is recoverable: the prior collection
                    # succeeded, but its final-store transaction did not.
                    if inserted or recoverable or include_duplicates:
                        emitted_docs.append(item)
                append_jsonl(items_path, emitted_docs)

            # Advance only after the source completed successfully and after
            # all candidate items were persisted.  Never derive this from the
            # snapshot filename/order or move it backwards.
            if not dry_run and candidate_items:
                dated = [
                    i for i in candidate_items
                    if (i.get("timestamps") or {}).get("created_at") and _cursor_eligible(i, source)
                ]
                if dated:
                    latest = max(dated, key=lambda i: str((i.get("timestamps") or {}).get("created_at")))
                    state.advance_cursor(
                        source_id,
                        (latest.get("timestamps") or {}).get("created_at"),
                        (latest.get("external") or {}).get("id"),
                        context.run_id,
                    )
                    if source_type == "discord":
                        _advance_main_cursor(
                            context.base_dir / "data" / "quant_intel.sqlite",
                            source_id,
                            latest,
                            context.run_id,
                        )

            item_count = len(result.items)
            state.finish_source(
                run_id=context.run_id,
                source_id=source_id,
                attempt=attempt,
                status="success",
                item_count=item_count,
                new_count=new_count,
                duplicate_count=duplicate_count,
            )
            return {
                "id": source_id,
                "type": source_type,
                "status": "success",
                "attempt": attempt,
                "item_count": item_count,
                "candidate_count": len(candidate_items),
                "cursor": cursor,
                "cursor_cutoff": cutoff.isoformat() if cutoff else None,
                "new_count": new_count,
                "duplicate_count": duplicate_count,
                "emitted_count": len(emitted_docs),
                "artifacts": result.artifacts,
                "stats": result.stats,
                "planned_commands": result.planned_commands,
            }
        except Exception as exc:  # noqa: BLE001 - source isolation is intentional.
            last_error = str(exc)
            state.finish_source(
                run_id=context.run_id,
                source_id=source_id,
                attempt=attempt,
                status="failed",
                item_count=0,
                new_count=0,
                duplicate_count=0,
                error=last_error,
            )
            append_jsonl(
                errors_path,
                [
                    {
                        "run_id": context.run_id,
                        "source_id": source_id,
                        "source_type": source_type,
                        "attempt": attempt,
                        "error": last_error,
                        "at": utc_now_iso(),
                    }
                ],
            )
            if attempt < attempts:
                time.sleep(retry_backoff_seconds)

    return {
        "id": source_id,
        "type": source_type,
        "status": "failed",
        "attempt": attempts,
        "item_count": 0,
        "new_count": 0,
        "duplicate_count": 0,
        "emitted_count": 0,
        "artifacts": [],
        "stats": {},
        "planned_commands": [],
        "error": last_error,
    }
