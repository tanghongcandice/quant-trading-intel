from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .base import AdapterContext, AdapterResult, SourceAdapter
from ..models import build_information_item
from ..utils import command_for_log, ensure_dir, read_json, run_subprocess, safe_slug, write_text


DEFAULT_DISCORD_EXPORTER = "/Users/bytedance/.codex/skills/discord-crawler/scripts/discord_exporter.py"


class DiscordAdapter(SourceAdapter):
    source_type = "discord"
    adapter_version = "0.1.0"

    def collect(self, source: dict[str, Any], context: AdapterContext) -> AdapterResult:
        source_id = source["id"]
        raw_dir = ensure_dir(context.raw_dir / source_id)
        fixture_file = source.get("fixture_file")

        if fixture_file:
            fixture_path = self._resolve_path(fixture_file, context.base_dir)
            docs = self._load_export(fixture_path)
            return self._result_from_docs(source, context, docs, [str(fixture_path)], [])

        command, output_path = self._build_command(source, context.base_dir, raw_dir)
        if context.dry_run:
            return AdapterResult(
                source_id=source_id,
                source_type=self.source_type,
                stats={
                    "mode": source.get("mode", "export"),
                    "dry_run": True,
                    "requires_env": "DISCORD_TOKEN",
                    "channel_id": source.get("channel_id"),
                    "target_author_count": len(source.get("target_authors") or []),
                },
                planned_commands=[command_for_log(command)],
            )

        if not os.environ.get("DISCORD_TOKEN"):
            raise RuntimeError(
                f"discord source {source_id} needs DISCORD_TOKEN with access to channel {source.get('channel_id')}"
            )

        result = run_subprocess(command, timeout_seconds=context.timeout_seconds, env=os.environ.copy())
        write_text(raw_dir / "stdout.log", result.stdout)
        write_text(raw_dir / "stderr.log", result.stderr)
        write_text(raw_dir / "command.json", json.dumps({"command": command_for_log(command)}, indent=2))
        if result.returncode != 0:
            raise RuntimeError(f"discord source {source_id} failed with code {result.returncode}: {result.stderr.strip()}")

        docs = self._load_export(output_path)
        return self._result_from_docs(
            source,
            context,
            docs,
            [str(output_path), str(raw_dir / "stdout.log"), str(raw_dir / "stderr.log")],
            [command_for_log(command)],
        )

    def _build_command(self, source: dict[str, Any], base_dir: Path, raw_dir: Path) -> tuple[list[str], Path]:
        mode = source.get("mode", "export")
        if mode != "export":
            raise ValueError(f"Unsupported discord mode for {source['id']}: {mode}")

        exporter = self._resolve_path(source.get("script") or DEFAULT_DISCORD_EXPORTER, base_dir)
        output_path = raw_dir / f"{safe_slug(source['id'])}.json"
        cmd = [sys.executable, str(exporter)] if str(exporter).endswith(".py") else [str(exporter)]
        cmd.extend(
            [
                "export",
                "--channel",
                str(source["channel_id"]),
                "--output",
                str(output_path),
                "--format",
                "Json",
            ]
        )

        for key, flag in (("after", "--after"), ("before", "--before")):
            if source.get(key):
                cmd.extend([flag, str(source[key])])
        if source.get("include_threads"):
            cmd.extend(["--include-threads", str(source["include_threads"])])
        if source.get("reverse"):
            cmd.append("--reverse")
        return cmd, output_path

    def _resolve_path(self, path_value: str, base_dir: Path) -> Path:
        path = Path(path_value).expanduser()
        if path.is_absolute():
            return path
        return (base_dir / path).resolve()

    def _load_export(self, path: Path) -> list[dict[str, Any]]:
        payload = read_json(path)
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        messages = payload.get("messages") or payload.get("Messages") or []
        if not isinstance(messages, list):
            return []
        return messages

    def _result_from_docs(
        self,
        source: dict[str, Any],
        context: AdapterContext,
        docs: list[dict[str, Any]],
        artifacts: list[str],
        planned_commands: list[list[str]],
    ) -> AdapterResult:
        filtered = self._filter_docs(source, docs)
        items = [self._normalize_message(source, context, doc) for doc in filtered]
        return AdapterResult(
            source_id=source["id"],
            source_type=self.source_type,
            items=items,
            artifacts=artifacts,
            stats={
                "mode": source.get("mode", "export"),
                "raw_count": len(docs),
                "filtered_count": len(filtered),
                "normalized_count": len(items),
            },
            planned_commands=planned_commands,
        )

    def _filter_docs(self, source: dict[str, Any], docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        targets = [self._normalize_author_name(name) for name in source.get("target_authors") or []]
        target_ids = {str(value) for value in source.get("target_author_ids") or [] if value}
        if not targets and not target_ids:
            return docs

        filtered = []
        for doc in docs:
            author = doc.get("author") or doc.get("Author") or {}
            author_id = str(author.get("id") or author.get("Id") or "")
            names = [
                author.get("name"),
                author.get("username"),
                author.get("nickname"),
                author.get("displayName"),
                author.get("globalName"),
                doc.get("author"),
            ]
            normalized_names = [self._normalize_author_name(name) for name in names if name]
            if author_id and author_id in target_ids:
                filtered.append(doc)
            elif any(any(target in name or name in target for target in targets) for name in normalized_names):
                filtered.append(doc)
        return filtered

    def _normalize_message(self, source: dict[str, Any], context: AdapterContext, data: dict[str, Any]) -> dict[str, Any]:
        author = data.get("author") or data.get("Author") or {}
        message_id = data.get("id") or data.get("Id") or data.get("messageId") or data.get("MessageId")
        guild_id = str(source.get("guild_id") or "")
        channel_id = str(source.get("channel_id") or "")
        channel_name = source.get("channel_name")
        server_name = source.get("server_name")
        external_url = None
        if guild_id and channel_id and message_id:
            external_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"

        author_name = self._author_display_name(author, data)
        content = self._message_content(data)
        title = self._message_title(content)
        timestamp = (
            data.get("timestamp")
            or data.get("Timestamp")
            or data.get("timestampUtc")
            or data.get("timestampUtcFromSnowflake")
            or data.get("createdAt")
        )

        return build_information_item(
            source_type=self.source_type,
            source_id=source["id"],
            source_name=source.get("name") or f"{server_name or guild_id} / {channel_name or channel_id}",
            collector="discord-crawler",
            adapter_version=self.adapter_version,
            tags=source.get("tags", []),
            external_id=str(message_id) if message_id else None,
            external_url=data.get("url") or data.get("Url") or external_url,
            title=title,
            content_text=content,
            language=source.get("language"),
            author={
                "external_id": str(author.get("id") or author.get("Id") or "") or None,
                "handle": author.get("username") or author.get("name"),
                "display_name": author_name,
                "profile_url": None,
                "metadata": {
                    "server": server_name,
                    "channel": channel_name,
                    "guild_id": guild_id or None,
                    "channel_id": channel_id or None,
                },
            },
            created_at=timestamp,
            collected_at=context.collected_at,
            metrics={
                "reply_count": self._count_collection(data.get("replies") or data.get("Replies")),
                "reaction_count": self._count_reactions(data.get("reactions") or data.get("Reactions")),
                "attachment_count": self._count_collection(data.get("attachments") or data.get("Attachments")),
            },
            raw_payload={
                "discord": data,
                "source_config_id": source["id"],
                "guild_id": guild_id or None,
                "channel_id": channel_id or None,
                "server_name": server_name,
                "channel_name": channel_name,
                "target_authors": source.get("target_authors") or [],
            },
        )

    def _author_display_name(self, author: dict[str, Any], data: dict[str, Any]) -> str | None:
        return (
            author.get("displayName")
            or author.get("globalName")
            or author.get("nickname")
            or author.get("name")
            or author.get("username")
            or (data.get("author") if isinstance(data.get("author"), str) else None)
        )

    def _message_content(self, data: dict[str, Any]) -> str | None:
        content = data.get("content") or data.get("Content") or data.get("text") or data.get("rawText")
        if content:
            return str(content).strip()
        embed_texts = []
        for embed in data.get("embeds") or data.get("Embeds") or []:
            if isinstance(embed, dict):
                for key in ("title", "description", "url"):
                    if embed.get(key):
                        embed_texts.append(str(embed[key]))
        return "\n".join(embed_texts).strip() or None

    def _message_title(self, content: str | None) -> str | None:
        if not content:
            return None
        compact = re.sub(r"\s+", " ", content).strip()
        return compact[:80] if len(compact) > 120 else None

    def _normalize_author_name(self, value: Any) -> str:
        text = str(value or "").lower()
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _count_collection(self, value: Any) -> int | None:
        if isinstance(value, list):
            return len(value)
        return None

    def _count_reactions(self, value: Any) -> int | None:
        if not isinstance(value, list):
            return None
        total = 0
        for reaction in value:
            if isinstance(reaction, dict):
                total += int(reaction.get("count") or reaction.get("Count") or 1)
            else:
                total += 1
        return total
