from __future__ import annotations

import hashlib
import mimetypes
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .utils import ensure_dir, safe_slug


STATIC_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
EXTENSION_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/avif": ".avif",
}


def _looks_animated(data: bytes, extension: str) -> bool:
    if data.startswith((b"GIF87a", b"GIF89a")):
        return True
    if extension == ".png" and b"acTL" in data[:65536]:
        return True
    if extension == ".webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        offset = 12
        while offset + 8 <= min(len(data), 65536):
            chunk = data[offset : offset + 4]
            size = int.from_bytes(data[offset + 4 : offset + 8], "little")
            if chunk == b"ANIM":
                return True
            offset += 8 + size + (size % 2)
    return False


def _candidate_extension(url: str, content_type: str) -> str:
    mime = content_type.split(";", 1)[0].lower().strip()
    if mime in EXTENSION_BY_MIME:
        return EXTENSION_BY_MIME[mime]
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in STATIC_EXTENSIONS:
        return suffix
    guessed = mimetypes.guess_extension(mime) or ""
    return guessed if guessed in STATIC_EXTENSIONS else ""


def download_static_images(
    candidates: list[dict[str, Any]],
    *,
    media_root: Path,
    source_id: str,
    external_id: str,
    timeout_seconds: int = 30,
    max_bytes: int = 20 * 1024 * 1024,
) -> list[dict[str, Any]]:
    output_dir = ensure_dir(media_root / safe_slug(source_id) / safe_slug(external_id))
    saved: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        url = str(candidate.get("url") or "").strip()
        declared_type = str(candidate.get("type") or candidate.get("content_type") or "").lower()
        filename = str(candidate.get("filename") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        if "gif" in declared_type or "video" in declared_type or filename.lower().endswith(".gif"):
            continue
        request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "image/avif,image/webp,image/png,image/jpeg"})
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                content_type = str(response.headers.get("Content-Type") or declared_type)
                if not content_type.lower().startswith("image/"):
                    continue
                length = int(response.headers.get("Content-Length") or 0)
                if length and length > max_bytes:
                    continue
                data = response.read(max_bytes + 1)
        except Exception:
            continue
        if not data or len(data) > max_bytes:
            continue
        extension = _candidate_extension(url, content_type)
        if not extension or _looks_animated(data, extension):
            continue
        digest = hashlib.sha256(data).hexdigest()
        path = output_dir / f"{len(saved) + 1:02d}-{digest[:12]}{extension}"
        path.write_bytes(data)
        relative = path.relative_to(media_root).as_posix()
        saved.append(
            {
                "kind": "static_image",
                "filename": path.name,
                "mime_type": content_type.split(";", 1)[0],
                "bytes": len(data),
                "sha256": digest,
                "local_path": str(path),
                "api_url": f"/media/{relative}",
                "source_url": url,
            }
        )
    return saved


def x_image_candidates(media: Any) -> list[dict[str, Any]]:
    if isinstance(media, list):
        return x_image_candidates({"photos": media})
    if not isinstance(media, dict):
        return []
    # Crawlers may wrap the platform payload under ``remote``.
    if isinstance(media.get("remote"), dict):
        media = media["remote"]
    values: list[dict[str, Any]] = []
    for key in ("photos", "images"):
        for item in media.get(key) or []:
            if isinstance(item, str):
                values.append({"url": item, "type": "image"})
            elif isinstance(item, dict):
                values.append(
                    {
                        "url": item.get("url") or item.get("media_url_https") or item.get("mediaUrl"),
                        "type": item.get("type") or "image",
                        "filename": item.get("filename") or "",
                    }
                )
    # Legacy snapshots sometimes store media as a bare remote URL list.
    remote = media.get("remote")
    if isinstance(remote, list):
        values.extend(x_image_candidates(remote))
    return values


def discord_image_candidates(data: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for item in data.get("attachments") or data.get("Attachments") or []:
        if not isinstance(item, dict):
            continue
        values.append(
            {
                "url": item.get("url") or item.get("Url") or item.get("proxyUrl") or item.get("ProxyUrl"),
                "type": item.get("contentType") or item.get("ContentType") or "",
                "filename": item.get("fileName") or item.get("FileName") or item.get("filename") or "",
            }
        )
    for embed in data.get("embeds") or data.get("Embeds") or []:
        if not isinstance(embed, dict):
            continue
        for key in ("image", "thumbnail", "Image", "Thumbnail"):
            image = embed.get(key)
            if isinstance(image, dict):
                values.append({"url": image.get("url") or image.get("Url"), "type": "image"})
    return values
