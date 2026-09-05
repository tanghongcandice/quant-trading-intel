from __future__ import annotations

from .adapters.base import SourceAdapter
from .adapters.discord import DiscordAdapter
from .adapters.substack import SubstackAdapter
from .adapters.x import XAdapter
from .adapters.douyin import DouyinAdapter


ADAPTERS: dict[str, type[SourceAdapter]] = {
    "discord": DiscordAdapter,
    "x": XAdapter,
    "substack": SubstackAdapter,
    "douyin": DouyinAdapter,
}


def adapter_for(source_type: str) -> SourceAdapter:
    adapter_cls = ADAPTERS.get(source_type)
    if not adapter_cls:
        known = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"Unknown source type: {source_type}. Known types: {known}")
    return adapter_cls()
