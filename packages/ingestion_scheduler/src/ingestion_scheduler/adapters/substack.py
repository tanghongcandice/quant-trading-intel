from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .base import AdapterContext, AdapterResult, SourceAdapter
from ..models import build_information_item
from ..utils import command_for_log, ensure_dir, resolve_path, run_subprocess, safe_slug, write_text


DEFAULT_SUBSTACK_SCRIPT = ""


class SubstackAdapter(SourceAdapter):
    source_type = "substack"
    adapter_version = "0.1.0"

    def collect(self, source: dict[str, Any], context: AdapterContext) -> AdapterResult:
        source_id = source["id"]
        raw_dir = ensure_dir(context.raw_dir / source_id)
        fixture_dir = source.get("fixture_dir")
        browser_snapshot = source.get("browser_snapshot")

        if context.dry_run:
            return AdapterResult(
                source_id=source_id,
                source_type=self.source_type,
                stats={"mode": source.get("mode", "download"), "dry_run": True},
            )

        if source.get("mode") == "browser_session":
            if not browser_snapshot:
                return AdapterResult(source_id, self.source_type, stats={"mode": "browser_session", "skipped": True, "reason": "browser_snapshot_not_configured"})
            path = resolve_path(browser_snapshot, context.base_dir)
            if not path.exists():
                return AdapterResult(source_id, self.source_type, stats={"mode": "browser_session", "skipped": True, "reason": "browser_snapshot_missing", "snapshot": str(path)})
            payload = json.loads(path.read_text(encoding="utf-8"))
            posts = payload if isinstance(payload, list) else payload.get("items", [payload])
            items = [self._normalize_browser_post(source, context, post) for post in posts if isinstance(post, dict)]
            return AdapterResult(source_id, self.source_type, items=items, artifacts=[str(path)], stats={"mode": "browser_session", "normalized_count": len(items)})

        if fixture_dir:
            input_dir = resolve_path(fixture_dir, context.base_dir)
            items = [self._normalize_markdown(source, context, path) for path in self._markdown_files(input_dir)]
            return AdapterResult(
                source_id=source_id,
                source_type=self.source_type,
                items=items,
                artifacts=[str(input_dir)],
                stats={"mode": "fixture_dir", "normalized_count": len(items)},
            )

        mode = source.get("mode", "download")
        command, output_dir = self._build_command(source, raw_dir)
        result = run_subprocess(command, timeout_seconds=context.timeout_seconds)
        write_text(raw_dir / "stdout.log", result.stdout)
        write_text(raw_dir / "stderr.log", result.stderr)
        write_text(raw_dir / "command.json", json.dumps({"command": command_for_log(command)}, indent=2))
        if result.returncode != 0:
            raise RuntimeError(f"substack source {source_id} failed with code {result.returncode}: {result.stderr.strip()}")

        if mode == "list":
            items = self._items_from_list_stdout(source, context, result.stdout)
            write_text(raw_dir / "urls.txt", "\n".join([item["external"]["url"] or "" for item in items]))
        else:
            items = [self._normalize_markdown(source, context, path) for path in self._markdown_files(output_dir)]

        return AdapterResult(
            source_id=source_id,
            source_type=self.source_type,
            items=items,
            artifacts=[str(output_dir), str(raw_dir / "stdout.log"), str(raw_dir / "stderr.log")],
            stats={"mode": mode, "normalized_count": len(items)},
            planned_commands=[command_for_log(command)],
        )

    def _normalize_browser_post(self, source: dict[str, Any], context: AdapterContext, post: dict[str, Any]) -> dict[str, Any]:
        external_url = post.get("url") or source.get("url")
        host = urlparse(external_url or "").netloc
        return build_information_item(
            source_type=self.source_type, source_id=source["id"],
            source_name=source.get("name") or host or source["id"],
            collector="browser-session", adapter_version=self.adapter_version,
            tags=source.get("tags", []), external_id=external_url or post.get("title"),
            external_url=external_url, title=post.get("title"),
            content_text=post.get("content_html") or post.get("content") or "",
            language=source.get("language"), author={"external_id": host.split(".")[0] if host else None,
            "handle": host.split(".")[0] if host else None, "display_name": source.get("name"),
            "profile_url": source.get("url"), "metadata": {}},
            created_at=post.get("published") or post.get("created_at"), collected_at=context.collected_at,
            metrics={}, raw_payload={"browser_snapshot": post, "source_config_id": source["id"]})

    def _build_command(self, source: dict[str, Any], raw_dir: Path) -> tuple[list[str], Path]:
        script = source.get("script") or DEFAULT_SUBSTACK_SCRIPT
        if not script:
            raise RuntimeError("Substack command-line crawler has been removed; provide a browser_session snapshot")
        mode = source.get("mode", "download")
        url = source["url"]
        output_dir = raw_dir / "download"
        cmd = [script, mode, url]

        if mode == "download":
            cmd.extend(["--output", str(output_dir), "--format", source.get("format", "md")])
            if source.get("download_images") is False:
                cmd.append("--no-download-images")
            if source.get("download_files"):
                cmd.append("--download-files")
            if source.get("image_quality"):
                cmd.extend(["--image-quality", source["image_quality"]])
        elif mode != "list":
            raise ValueError(f"Unsupported substack mode for {source['id']}: {mode}")

        for key, flag in (("after", "--after"), ("before", "--before"), ("proxy", "--proxy")):
            if source.get(key):
                cmd.extend([flag, str(source[key])])
        if source.get("rate") is not None:
            cmd.extend(["--rate", str(source["rate"])])
        if source.get("verbose"):
            cmd.append("--verbose")
        return cmd, output_dir

    def _markdown_files(self, input_dir: Path) -> list[Path]:
        if not input_dir.exists():
            return []
        return sorted(
            path
            for path in input_dir.rglob("*.md")
            if path.name != "index.md" and "/images/" not in str(path) and "/files/" not in str(path)
        )

    def _normalize_markdown(self, source: dict[str, Any], context: AdapterContext, path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8", errors="replace")
        title = self._title_from_markdown(text) or path.stem
        external_url = self._source_url_from_markdown(text)
        created_at = self._created_at_from_filename(path.name)
        publication_url = source.get("url") or external_url
        publication_host = urlparse(publication_url or "").netloc
        author_handle = publication_host.split(".")[0] if publication_host else None

        return build_information_item(
            source_type=self.source_type,
            source_id=source["id"],
            source_name=source.get("name") or publication_host or source["id"],
            collector="substack-crawler",
            adapter_version=self.adapter_version,
            tags=source.get("tags", []),
            external_id=external_url or path.stem,
            external_url=external_url,
            title=title,
            content_text=text,
            language=source.get("language"),
            author={
                "external_id": author_handle,
                "handle": author_handle,
                "display_name": source.get("author_name") or source.get("name"),
                "profile_url": publication_url,
                "metadata": {"publication_url": publication_url, "publication_host": publication_host},
            },
            created_at=created_at,
            collected_at=context.collected_at,
            metrics={},
            raw_payload={"markdown_path": str(path), "source_config_id": source["id"]},
        )

    def _items_from_list_stdout(
        self, source: dict[str, Any], context: AdapterContext, stdout: str
    ) -> list[dict[str, Any]]:
        urls: list[str] = []
        seen = set()
        for match in re.finditer(r"https?://[^\s\"')]+", stdout):
            url = match.group(0).rstrip(".,")
            if url not in seen:
                urls.append(url)
                seen.add(url)
        items = []
        for url in urls:
            host = urlparse(url).netloc
            slug = url.rstrip("/").rsplit("/", 1)[-1]
            items.append(
                build_information_item(
                    source_type=self.source_type,
                    source_id=source["id"],
                    source_name=source.get("name") or host or source["id"],
                    collector="substack-crawler",
                    adapter_version=self.adapter_version,
                    tags=source.get("tags", []),
                    external_id=url,
                    external_url=url,
                    title=slug.replace("-", " "),
                    content_text=url,
                    author={
                        "external_id": host.split(".")[0] if host else None,
                        "handle": host.split(".")[0] if host else None,
                        "display_name": source.get("name"),
                        "profile_url": source.get("url"),
                        "metadata": {"publication_host": host},
                    },
                    collected_at=context.collected_at,
                    raw_payload={"list_url": url, "source_config_id": source["id"]},
                )
            )
        return items

    def _title_from_markdown(self, text: str) -> str | None:
        for line in text.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return None

    def _source_url_from_markdown(self, text: str) -> str | None:
        match = re.search(r"^original content:\s*(https?://\S+)\s*$", text, flags=re.IGNORECASE | re.MULTILINE)
        return match.group(1) if match else None

    def _created_at_from_filename(self, name: str) -> str | None:
        match = re.match(r"^(\d{8})_(\d{6})_", name)
        if not match:
            return None
        date_part, time_part = match.groups()
        return (
            f"{date_part[0:4]}-{date_part[4:6]}-{date_part[6:8]}T"
            f"{time_part[0:2]}:{time_part[2:4]}:{time_part[4:6]}Z"
        )
