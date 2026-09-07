from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class AdapterContext:
    base_dir: Path
    run_id: str
    run_dir: Path
    raw_dir: Path
    collected_at: str
    dry_run: bool
    timeout_seconds: int
    # Read-only lookup into the scheduler's durable processing ledger.  Adapters
    # use this before expensive media/enrichment work; final dedupe still runs
    # transactionally in the runner and ingestion service.
    processed_item: Callable[[str, str], dict[str, Any] | None] | None = None


@dataclass
class AdapterResult:
    source_id: str
    source_type: str
    items: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    planned_commands: list[list[str]] = field(default_factory=list)


class SourceAdapter:
    source_type = "base"
    adapter_version = "0.1.0"

    def collect(self, source: dict[str, Any], context: AdapterContext) -> AdapterResult:
        raise NotImplementedError
