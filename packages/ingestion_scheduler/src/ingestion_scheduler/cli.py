from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import load_config, run_scheduler, validate_config
from .state import StateStore


def cmd_run(args: argparse.Namespace) -> None:
    summary = run_scheduler(
        config_path=Path(args.config).resolve(),
        run_id=args.run_id,
        only=args.only,
        include_disabled=args.include_disabled,
        include_duplicates=args.include_duplicates,
        dry_run=args.dry_run,
        fail_fast=args.fail_fast,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def cmd_validate(args: argparse.Namespace) -> None:
    config = load_config(Path(args.config).resolve())
    validate_config(config)
    print(json.dumps({"ok": True, "sources": len(config.get("sources", []))}, indent=2))


def cmd_status(args: argparse.Namespace) -> None:
    state = StateStore(Path(args.db).resolve())
    try:
        print(json.dumps(state.counts(), ensure_ascii=False, indent=2, sort_keys=True))
    finally:
        state.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run unified market information ingestion jobs")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="run configured sources")
    p.add_argument("--config", required=True, help="path to source config JSON")
    p.add_argument("--run-id", help="optional deterministic run id")
    p.add_argument("--only", action="append", help="run one source id; can be repeated")
    p.add_argument("--include-disabled", action="store_true", help="allow disabled sources to run")
    p.add_argument("--include-duplicates", action="store_true", help="emit duplicate items into run items.jsonl")
    p.add_argument("--dry-run", action="store_true", help="show planned commands without external collection")
    p.add_argument("--fail-fast", action="store_true", help="stop after the first failed source")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("validate", help="validate config shape and known adapters")
    p.add_argument("--config", required=True, help="path to source config JSON")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("status", help="show state database counts")
    p.add_argument("--db", required=True, help="path to ingestion_state.sqlite")
    p.set_defaults(func=cmd_status)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
