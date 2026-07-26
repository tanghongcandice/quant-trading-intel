#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT/apps/api"
WEB_DIR="$ROOT/apps/web"
DB_PATH="$ROOT/data/quant_intel.sqlite"
PYTHON_BIN="${PYTHON_BIN:-python3}"
NODE_BIN="${NODE_BIN:-node}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
API_BASE="http://$API_HOST:$API_PORT"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/quant-intel-verify.XXXXXX")"
server_pid=""

if [[ "$PYTHON_BIN" == */* ]]; then
  PYTHON_BIN="$(cd "$(dirname "$PYTHON_BIN")" && pwd)/$(basename "$PYTHON_BIN")"
fi
if [[ "$NODE_BIN" == */* ]]; then
  NODE_BIN="$(cd "$(dirname "$NODE_BIN")" && pwd)/$(basename "$NODE_BIN")"
fi

cleanup() {
  if [[ -n "$server_pid" ]]; then
    kill "$server_pid" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

fail() {
  printf '\nVERIFY FAILED: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing command: $1"
}

api_get_json() {
  "$PYTHON_BIN" - "$1" <<'PY'
import json
import sys
import urllib.request

url = sys.argv[1]
with urllib.request.urlopen(url, timeout=10) as response:
    payload = response.read().decode("utf-8")
data = json.loads(payload)
print(json.dumps(data, ensure_ascii=False, sort_keys=True))
PY
}

log "Checking local tools"
require_cmd sqlite3
require_cmd "$PYTHON_BIN"
require_cmd "$NODE_BIN"

log "Checking database integrity and counts"
[[ -f "$DB_PATH" ]] || fail "Database not found: $DB_PATH"
integrity="$(sqlite3 "$DB_PATH" 'PRAGMA integrity_check;')"
[[ "$integrity" == "ok" ]] || fail "SQLite integrity_check returned: $integrity"

counts="$("$PYTHON_BIN" - "$DB_PATH" <<'PY'
import sqlite3
import sys

db = sys.argv[1]
conn = sqlite3.connect(db)
checks = {
    "information_items": 122,
    "item_entities": 282,
    "information_items_fts": 122,
}
for table, expected in checks.items():
    actual = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"{table}={actual}")
    if actual != expected:
        raise SystemExit(f"{table} expected {expected}, got {actual}")
print("database_counts=ok")
PY
)"
printf '%s\n' "$counts"

log "Checking backend CLI query"
cd "$API_DIR"
query_json="$(PYTHONPATH=. "$PYTHON_BIN" -m app.jobs.query_items --ticker MU --limit 5)"
query_file="$TMP_DIR/query.json"
printf '%s\n' "$query_json" > "$query_file"
"$PYTHON_BIN" - "$query_file" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
items = data.get("items") or []
if not items:
    raise SystemExit("query_items returned no items")
if not any("MU" in (item.get("tickers") or []) for item in items):
    raise SystemExit("query_items did not return MU-tagged items")
print(f"query_items=ok item_id={items[0]['id']}")
PY
sample_item_id="$("$PYTHON_BIN" - "$query_file" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["items"][0]["id"])
PY
)"

log "Checking backend context generation"
context_text="$(PYTHONPATH=. "$PYTHON_BIN" -m app.jobs.build_context "$sample_item_id")"
grep -q "数据进阶分析请求" <<<"$context_text" || fail "Context output is missing expected heading"
grep -q "$sample_item_id" <<<"$context_text" || fail "Context output is missing item id"
printf 'build_context=ok item_id=%s\n' "$sample_item_id"

log "Checking ingestion scheduler dry-run"
dry_run_json="$(PYTHONPATH=. "$PYTHON_BIN" -m app.jobs.collect_premarket --dry-run --run-id verify_dry_run)"
dry_run_file="$TMP_DIR/dry_run.json"
printf '%s\n' "$dry_run_json" > "$dry_run_file"
"$PYTHON_BIN" - "$dry_run_file" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
if data.get("status") != "success":
    raise SystemExit(f"dry-run status was {data.get('status')}")
summary = data.get("scheduler_summary") or {}
if not summary.get("dry_run"):
    raise SystemExit("scheduler_summary.dry_run was not true")
if (summary.get("totals") or {}).get("failed_sources") != 0:
    raise SystemExit("dry-run had failed sources")
print("collect_premarket_dry_run=ok")
PY

log "Checking frontend files"
[[ -f "$WEB_DIR/index.html" ]] || fail "Front-end index.html missing"
[[ -f "$WEB_DIR/src/app.js" ]] || fail "Front-end app.js missing"
"$NODE_BIN" --check "$WEB_DIR/src/app.js"
grep -q "fetchApiItems" "$WEB_DIR/src/app.js" || fail "Front-end does not contain API loading path"
grep -q "__HIGH_QUALITY_ITEMS__" "$WEB_DIR/data/sample_items.js" || fail "Front-end sample data missing"
printf 'frontend=ok\n'

log "Checking FastAPI dependency"
"$PYTHON_BIN" - <<'PY'
try:
    import fastapi  # noqa: F401
    import uvicorn  # noqa: F401
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing FastAPI runtime dependency: "
        f"{exc.name}. Install from apps/api with: python3 -m pip install -e ."
    )
print("fastapi_dependencies=ok")
PY

log "Starting temporary FastAPI service"
cd "$API_DIR"
PYTHONPATH=. "$PYTHON_BIN" -m uvicorn app.main:app --host "$API_HOST" --port "$API_PORT" >/tmp/quant_intel_uvicorn.log 2>&1 &
server_pid=$!

for _ in $(seq 1 30); do
  if api_get_json "$API_BASE/health" >/tmp/quant_intel_health.json 2>/dev/null; then
    break
  fi
  sleep 0.5
done

[[ -s /tmp/quant_intel_health.json ]] || {
  cat /tmp/quant_intel_uvicorn.log >&2 || true
  fail "FastAPI service did not start"
}

log "Checking FastAPI endpoints"
health_json="$(cat /tmp/quant_intel_health.json)"
health_file="$TMP_DIR/health.json"
printf '%s\n' "$health_json" > "$health_file"
"$PYTHON_BIN" - "$health_file" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
if data.get("status") != "ok":
    raise SystemExit(f"health status was {data.get('status')}")
print("api_health=ok")
PY

items_json="$(api_get_json "$API_BASE/api/items?ticker=MU&limit=5")"
items_file="$TMP_DIR/api_items.json"
printf '%s\n' "$items_json" > "$items_file"
"$PYTHON_BIN" - "$items_file" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
items = data.get("items") or []
if not items:
    raise SystemExit("/api/items returned no items")
if not any("MU" in (item.get("tickers") or []) for item in items):
    raise SystemExit("/api/items did not return MU-tagged items")
print(f"api_items=ok item_id={items[0]['id']}")
PY
api_item_id="$("$PYTHON_BIN" - "$items_file" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["items"][0]["id"])
PY
)"

context_json="$(api_get_json "$API_BASE/api/context/item/$api_item_id")"
context_file="$TMP_DIR/api_context.json"
printf '%s\n' "$context_json" > "$context_file"
"$PYTHON_BIN" - "$context_file" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
if not data.get("copy_text"):
    raise SystemExit("/api/context did not return copy_text")
if "数据进阶分析请求" not in data["copy_text"]:
    raise SystemExit("/api/context copy_text missing expected heading")
print("api_context=ok")
PY

runs_json="$(api_get_json "$API_BASE/api/runs?limit=5")"
runs_file="$TMP_DIR/api_runs.json"
printf '%s\n' "$runs_json" > "$runs_file"
"$PYTHON_BIN" - "$runs_file" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
if "runs" not in data:
    raise SystemExit("/api/runs did not return runs")
print("api_runs=ok")
PY

log "All local verification checks passed"
