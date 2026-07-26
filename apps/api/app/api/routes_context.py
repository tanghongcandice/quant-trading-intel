from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.services.context_service import build_item_context


def item_context(item_id: str, *, db_path: Optional[Path] = None, format: str = "markdown") -> dict:
    settings = get_settings(str(db_path) if db_path else None)
    return build_item_context(settings.db_path, item_id, format=format)
