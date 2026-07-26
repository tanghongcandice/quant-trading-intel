from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    for parent in [current, *current.parents]:
        if (parent / "quant-trading-intel").is_dir():
            return parent / "quant-trading-intel"
        if parent.name == "quant-trading-intel":
            return parent
    return current.parents[4]


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    db_path: Path


def get_settings(db_path: str | None = None) -> Settings:
    root = find_project_root()
    data_dir = root / "data"
    resolved_db = Path(db_path).expanduser().resolve() if db_path else data_dir / "quant_intel.sqlite"
    return Settings(project_root=root, data_dir=data_dir, db_path=resolved_db)
