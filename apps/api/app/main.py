from __future__ import annotations

try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:  # FastAPI is optional until the service dependencies are installed.
    FastAPI = None  # type: ignore
    HTTPException = Exception  # type: ignore
    Query = None  # type: ignore
    CORSMiddleware = None  # type: ignore

from app.core.config import get_settings
from app.services.context_service import build_item_context
from app.services.run_service import list_runs
from app.services.query_service import get_item, query_items


if FastAPI:
    app = FastAPI(title="Quant Trading Intel API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        settings = get_settings()
        return {"status": "ok", "db_path": str(settings.db_path)}

    @app.get("/api/items")
    def api_items(
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
        settings = get_settings()
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

    @app.get("/api/items/{item_id}")
    def api_item(item_id: str) -> dict:
        settings = get_settings()
        result = get_item(settings.db_path, item_id)
        if not result:
            raise HTTPException(status_code=404, detail="Item not found")
        return result

    @app.get("/api/context/item/{item_id}")
    def api_item_context(item_id: str, format: str = "markdown") -> dict:
        settings = get_settings()
        try:
            return build_item_context(settings.db_path, item_id, format=format)
        except KeyError:
            raise HTTPException(status_code=404, detail="Item not found")

    @app.get("/api/runs")
    def api_runs(limit: int = 50, offset: int = 0) -> dict:
        settings = get_settings()
        return list_runs(settings.db_path, limit=limit, offset=offset)

else:
    app = None
