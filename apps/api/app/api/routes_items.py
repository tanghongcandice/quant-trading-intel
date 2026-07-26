from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.services.query_service import get_item, query_items


def list_items(
    *,
    db_path: Optional[Path] = None,
    start_at: str | None = None,
    end_at: str | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    author: str | None = None,
    ticker: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    settings = get_settings(str(db_path) if db_path else None)
    return query_items(
        settings.db_path,
        start_at=start_at,
        end_at=end_at,
        source_type=source_type,
        source_id=source_id,
        author=author,
        ticker=ticker,
        q=q,
        limit=limit,
        offset=offset,
    )


def retrieve_item(item_id: str, *, db_path: Optional[Path] = None) -> dict | None:
    settings = get_settings(str(db_path) if db_path else None)
    return get_item(settings.db_path, item_id)
