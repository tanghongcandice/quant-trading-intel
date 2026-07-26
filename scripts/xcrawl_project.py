#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILL_SCRIPT = Path("/Users/bytedance/.codex/skills/x-crawler/scripts/xcrawl.py")


def main() -> None:
    skill_script = Path(os.environ.get("X_CRAWLER_SKILL_SCRIPT", DEFAULT_SKILL_SCRIPT)).expanduser()
    if not skill_script.exists():
        raise SystemExit(f"x-crawler helper not found: {skill_script}")

    spec = importlib.util.spec_from_file_location("codex_xcrawl_helper", skill_script)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load x-crawler helper: {skill_script}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    data_dir = Path(os.environ.get("X_CRAWLER_DATA_DIR", PROJECT_ROOT / "data" / "x_crawler")).expanduser()
    export_dir = Path(os.environ.get("X_CRAWLER_EXPORT_DIR", PROJECT_ROOT / "runs" / "x_crawler_exports")).expanduser()
    db_path = Path(os.environ.get("X_CRAWLER_DB_PATH", data_dir / "accounts.db")).expanduser()

    module.DATA_DIR = data_dir
    module.EXPORT_DIR = export_dir
    module.DB_PATH = db_path
    module.main()


if __name__ == "__main__":
    main()
