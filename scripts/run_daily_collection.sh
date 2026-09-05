#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT/apps/api"
DB_PATH="$ROOT/data/quant_intel.sqlite"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
RUN_ID="premarket_$(date -u '+%Y%m%dT%H%M%SZ')"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

log() {
  printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" "$*"
}

fail() {
  printf '\nDAILY COLLECTION FAILED: %s\n' "$*" >&2
  exit 1
}

log "Starting daily premarket collection: $RUN_ID"
cd "$API_DIR"
collection_json="/tmp/quant_intel_daily_collection_${RUN_ID}.json"
collection_failed=0

# Refresh all non-Douyin authenticated browser sources first.
browser_python="${BROWSER_REFRESH_PYTHON:-/Users/mac/.codex/skills/video-downloader/.runtime/douyin-downloader/.venv/bin/python}"
set +e
"$browser_python" "$ROOT/scripts/refresh_authenticated_snapshots.py" --root "$ROOT" --profiles "$ROOT/data/browser_profiles" >"/tmp/quant_intel_browser_refresh_${RUN_ID}.json"
browser_refresh_rc=$?
set -e
cat "/tmp/quant_intel_browser_refresh_${RUN_ID}.json"
if [[ "$browser_refresh_rc" -ne 0 ]]; then
  fail "Authenticated browser snapshot refresh failed; scheduler run skipped"
fi

# Refresh the persistent authenticated Douyin browser session before rebuilding
# snapshots. The profile is separate from the user's daily Chrome profile.
douyin_browser_python="${DOUYIN_BROWSER_PYTHON:-/Users/mac/.codex/skills/video-downloader/.runtime/douyin-downloader/.venv/bin/python}"
set +e
"$douyin_browser_python" "$ROOT/scripts/refresh_douyin_snapshots.py" --root "$ROOT" --profile-dir "$ROOT/data/browser_profiles/douyin" >"/tmp/quant_intel_douyin_refresh_${RUN_ID}.json"
refresh_rc=$?
set -e
cat "/tmp/quant_intel_douyin_refresh_${RUN_ID}.json"
if [[ "$refresh_rc" -ne 0 ]]; then
  fail "Douyin browser refresh failed; log in once in the dedicated profile and retry"
fi

# Rebuild Douyin snapshots and run the audio/ASR enrichment before the
# scheduler reads the built JSONL.  This keeps scheduled runs on the same
# project virtualenv and prevents stale browser captures from being reported
# as successful zero-new runs.
cd "$ROOT"
douyin_prepare_json="/tmp/quant_intel_douyin_prepare_${RUN_ID}.json"
set +e
PYTHONPATH="$ROOT/apps/api" "$PYTHON_BIN" scripts/prepare_douyin_ingestion.py --root "$ROOT" >"$douyin_prepare_json"
prepare_rc=$?
set -e
cat "$douyin_prepare_json"
if [[ "$prepare_rc" -ne 0 ]]; then
  collection_failed=1
fi
if [[ "$prepare_rc" -eq 0 ]]; then
  "$PYTHON_BIN" - "$douyin_prepare_json" <<'PY' || collection_failed=1
import json, sys
data=json.load(open(sys.argv[1], encoding="utf-8"))
bad=[p for p in data.get("profiles", []) if p.get("status") in {"stale_snapshot", "missing"}]
if bad:
    raise SystemExit("Douyin snapshot refresh required: " + ", ".join(p.get("source_id", "?") for p in bad))
PY
fi

if [[ "$collection_failed" -ne 0 ]]; then
  fail "Douyin snapshot preparation/refresh did not complete; scheduler run skipped"
fi

cd "$API_DIR"
set +e
PYTHONPATH=. "$PYTHON_BIN" -m app.jobs.collect_premarket --run-id "$RUN_ID" >"$collection_json"
collection_rc=$?
set -e
cat "$collection_json"

if [[ "$collection_rc" -ne 0 ]]; then
  collection_failed=1
fi

"$PYTHON_BIN" - "$collection_json" <<'PY' || collection_failed=1
import json
import sys

path = sys.argv[1]
try:
    data = json.load(open(path, encoding="utf-8"))
except Exception as exc:  # noqa: BLE001
    raise SystemExit(f"collection output was not valid JSON: {exc}")

summary = data.get("scheduler_summary") or {}
totals = summary.get("totals") or {}
failed_sources = totals.get("failed_sources", 0)
status = data.get("status")
scheduler_status = summary.get("status")

if status != "success" or scheduler_status != "success" or failed_sources:
    print(f"collection_status={status} scheduler_status={scheduler_status} failed_sources={failed_sources}", file=sys.stderr)
    for source in summary.get("sources") or []:
        if source.get("status") != "success":
            error = str(source.get("error") or "").replace("\n", " ")
            print(f"failed_source={source.get('id')} type={source.get('type')} error={error[:400]}", file=sys.stderr)
    raise SystemExit(1)

print(f"collection_status=ok run_id={summary.get('run_id')} new={totals.get('new', 0)} items={totals.get('items', 0)}")
PY

log "Checking SQLite integrity"
integrity="$(sqlite3 "$DB_PATH" 'PRAGMA integrity_check;')"
[[ "$integrity" == "ok" ]] || fail "SQLite integrity_check returned: $integrity"

log "Checking table baselines"
"$PYTHON_BIN" - "$DB_PATH" <<'PY'
import sqlite3
import sys

db = sys.argv[1]
conn = sqlite3.connect(db)
baselines = {
    "information_items": 122,
    # Entity extraction is now selective (not every item produces entities),
    # so the historical fixed count of 282 is no longer a valid health check.
    "item_entities": 0,
    "information_items_fts": 122,
}
for table, minimum in baselines.items():
    actual = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"{table}={actual}")
    if actual < minimum:
        raise SystemExit(f"{table} dropped below baseline {minimum}: {actual}")
PY

log "Checking query service"
PYTHONPATH=. "$PYTHON_BIN" -m app.jobs.query_items --limit 5 >/tmp/quant_intel_daily_query.json
"$PYTHON_BIN" - <<'PY'
import json

with open("/tmp/quant_intel_daily_query.json", encoding="utf-8") as fh:
    data = json.load(fh)
if not data.get("items"):
    raise SystemExit("query_items returned no items after daily collection")
print(f"query_items=ok total={data.get('total')}")
PY

if [[ "$collection_failed" -ne 0 ]]; then
  fail "Daily collection did not complete successfully; see $collection_json"
fi

log "Daily premarket collection completed successfully: $RUN_ID"
