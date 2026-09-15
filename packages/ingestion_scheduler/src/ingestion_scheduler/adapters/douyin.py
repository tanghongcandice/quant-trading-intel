from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone

from .base import AdapterContext, AdapterResult, SourceAdapter
from ..utils import ensure_dir, resolve_path


class DouyinAdapter(SourceAdapter):
    """Browser-first Douyin boundary; captured JSONL can be replayed."""

    source_type = "douyin"
    adapter_version = "0.1.0"

    def collect(self, source: dict, context: AdapterContext) -> AdapterResult:
        raw_dir = ensure_dir(context.raw_dir / source["id"])
        fixture = source.get("fixture_file") or source.get("browser_snapshot")
        if fixture:
            path = resolve_path(fixture, context.base_dir)
            if source.get('require_run_capture') and not context.dry_run:
                path = context.run_dir / 'group_items.jsonl'
            if not path.exists():
                if source.get('require_run_capture'):
                    raise RuntimeError('Group capture incomplete: same-run group_items.jsonl missing; inspect chrome_preflight_diagnostics.jsonl and group_checkpoint_status.json')
                raise RuntimeError(f"Douyin browser page data missing: {path}; run douyin_profile_extract.js in the signed-in profile page first")
            text = path.read_text(encoding="utf-8").strip()
            if source.get('require_run_capture') and not context.dry_run:
                receipt_path = context.run_dir / 'group_receipt.json'
                if not receipt_path.exists():
                    raise RuntimeError('Group not refreshed for this run: browser capture/voice transcription receipt missing; old snapshot refused')
                receipt = json.loads(receipt_path.read_text())
                validation_path = context.run_dir / 'chrome_preflight_validation.json'
                if not validation_path.exists() or json.loads(validation_path.read_text()).get('ready') is not True:
                    raise RuntimeError('Group preflight evidence has not passed validation')
                validation = json.loads(validation_path.read_text())
                diagnostics = context.run_dir / 'chrome_preflight_diagnostics.jsonl'
                if (validation.get('run_id') != context.run_id or
                        any(validation.get(key) != receipt.get(key) for key in ('sha256','capture_sha256')) or
                        not diagnostics.exists() or validation.get('diagnostics_sha256') != hashlib.sha256(diagnostics.read_bytes()).hexdigest()):
                    raise RuntimeError('Group evidence changed after validation; validate this run again')
                capture_path = context.run_dir / 'group_capture.json'
                if receipt.get('version') != 2 or not capture_path.exists() or receipt.get('capture_sha256') != hashlib.sha256(capture_path.read_bytes()).hexdigest():
                    raise RuntimeError('Group DOM capture hash/version mismatch')
                captured = datetime.fromisoformat(receipt['captured_at'].replace('Z', '+00:00'))
                if not 0 <= (datetime.now(timezone.utc)-captured).total_seconds() <= 7200:
                    raise RuntimeError('Group capture receipt expired')
                if (receipt.get('run_id') != context.run_id or receipt.get('status') != 'ready'
                        or receipt.get('pending_voice_count') != 0
                        or receipt.get('sha256') != hashlib.sha256(path.read_bytes()).hexdigest()):
                    raise RuntimeError('Group capture receipt mismatches this run or contains pending voices')
            # Browser bridge writes a single {author, works:[...]} snapshot;
            # retain compatibility with the historical JSONL format.
            try:
                parsed = json.loads(text)
                docs = ([parsed] if parsed.get("schema_version") else parsed.get("works", [])) if isinstance(parsed, dict) else parsed
            except json.JSONDecodeError:
                docs = [json.loads(line) for line in text.splitlines() if line.strip()]
            if docs and not all(doc.get("schema_version") for doc in docs):
                return AdapterResult(source["id"], self.source_type, stats={"mode": "browser_session", "skipped": True, "reason": "snapshot_requires_build"})
            if source.get("max_snapshot_age_hours") and not source.get('require_run_capture'):
                stamps = [(d.get("timestamps") or {}).get("collected_at") for d in docs]
                if not stamps or any(not stamp for stamp in stamps):
                    raise RuntimeError("Group snapshot has no collection timestamp")
                newest = max(datetime.fromisoformat(stamp.replace("Z", "+00:00")) for stamp in stamps)
                age = (datetime.now(timezone.utc) - newest).total_seconds() / 3600
                if age > float(source["max_snapshot_age_hours"]):
                    raise RuntimeError("Group snapshot is stale; refresh the authorized group in the signed-in browser")
            return AdapterResult(source["id"], self.source_type, docs, [str(path)], {"mode": "browser_session"})
        if context.dry_run:
            return AdapterResult(source["id"], self.source_type, stats={"mode": "browser_session", "dry_run": True})
        return AdapterResult(
            source["id"], self.source_type,
            stats={"mode": "browser_session", "skipped": True},
        )
