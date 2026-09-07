from __future__ import annotations

import json
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
            if not path.exists():
                raise RuntimeError(f"Douyin browser page data missing: {path}; run douyin_profile_extract.js in the signed-in profile page first")
            text = path.read_text(encoding="utf-8").strip()
            # Browser bridge writes a single {author, works:[...]} snapshot;
            # retain compatibility with the historical JSONL format.
            try:
                parsed = json.loads(text)
                docs = ([parsed] if parsed.get("schema_version") else parsed.get("works", [])) if isinstance(parsed, dict) else parsed
            except json.JSONDecodeError:
                docs = [json.loads(line) for line in text.splitlines() if line.strip()]
            if docs and not all(doc.get("schema_version") for doc in docs):
                return AdapterResult(source["id"], self.source_type, stats={"mode": "browser_session", "skipped": True, "reason": "snapshot_requires_build"})
            if source.get("max_snapshot_age_hours"):
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
