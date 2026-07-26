#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT/apps/api"
WORKSPACE_ROOT="$(cd "$ROOT/.." && pwd)"

cd "$API_DIR"

PYTHONPATH=. python3 -m app.jobs.init_db
PYTHONPATH=. python3 -m app.jobs.import_jsonl \
  --jsonl "$WORKSPACE_ROOT/outputs/high_quality_sources_20260619/high_quality_items.jsonl" \
  --mode historical_seed \
  --run-id run_seed_20260619_high_quality_sources

PYTHONPATH=. python3 -m app.jobs.import_report_snapshot \
  --report-date 2026-06-19 \
  --start-at 2026-06-15T16:00:00Z \
  --end-at 2026-06-19T13:58:00Z \
  --report-json "$WORKSPACE_ROOT/outputs/premarket_report_design/report_contract.v1.json" \
  --report-html "$WORKSPACE_ROOT/outputs/premarket_report_design/premarket_report_2026-06-19.html" \
  --item-count 122
