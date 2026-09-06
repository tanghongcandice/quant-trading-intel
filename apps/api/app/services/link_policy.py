"""URL-only author messages do not require translation."""
import re

URL = re.compile(r"https?://[^\s<>\"']+", re.I)


def author_text(item):
    raw = item.get("raw_payload") or {}
    discord = raw.get("discord") or {}
    text = discord.get("content")
    return text if isinstance(text, str) and text.strip() else (item.get("content") or {}).get("text") or ""


def is_link_only(item):
    text = author_text(item)
    return bool(URL.search(text)) and not URL.sub("", text).strip(" \t\r\n<>.,，。;；()（）")


def suppress_link_translation(item):
    if is_link_only(item):
        item.pop("translation", None)
        raw = item.setdefault("raw_payload", {})
        raw.pop("translation", None)
        raw["translation_policy"] = {"required": False, "status": "not_required", "reason": "url_only"}
