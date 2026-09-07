from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from .base import AdapterContext, AdapterResult, SourceAdapter
from ..models import build_information_item
from ..utils import command_for_log, ensure_dir, read_jsonl, resolve_path, run_subprocess, safe_slug, write_text
from ..media import download_static_images, x_image_candidates


DEFAULT_X_SCRIPT = ""


class XAdapter(SourceAdapter):
    source_type = "x"
    adapter_version = "0.1.0"

    def collect(self, source: dict[str, Any], context: AdapterContext) -> AdapterResult:
        source_id = source["id"]
        raw_dir = ensure_dir(context.raw_dir / source_id)
        fixture_file = source.get("fixture_file") or source.get("browser_snapshot")

        if context.dry_run:
            return AdapterResult(
                source_id=source_id,
                source_type=self.source_type,
                stats={"mode": source.get("mode", "search"), "dry_run": True},
            )

        if fixture_file:
            fixture_path = resolve_path(fixture_file, context.base_dir)
            if source.get("mode") == "browser_session":
                payload = json.loads(fixture_path.read_text(encoding="utf-8"))
                docs = payload if isinstance(payload, list) else payload.get("items", [])
            else:
                docs = read_jsonl(fixture_path)
            return self._result_from_docs(source, context, docs, [str(fixture_path)], [])

        command, output_path = self._build_command(source, context.base_dir, raw_dir)
        result = run_subprocess(command, timeout_seconds=context.timeout_seconds)
        write_text(raw_dir / "stdout.log", result.stdout)
        write_text(raw_dir / "stderr.log", result.stderr)
        write_text(raw_dir / "command.json", json.dumps({"command": command_for_log(command)}, indent=2))
        if result.returncode != 0:
            raise RuntimeError(f"x source {source_id} failed with code {result.returncode}: {result.stderr.strip()}")

        resolved_output = self._output_from_stdout(result.stdout) or output_path
        docs = read_jsonl(resolved_output)
        return self._result_from_docs(
            source,
            context,
            docs,
            [str(resolved_output), str(raw_dir / "stdout.log"), str(raw_dir / "stderr.log")],
            [command_for_log(command)],
        )

    def _build_command(self, source: dict[str, Any], base_dir: Path, raw_dir: Path) -> tuple[list[str], Path]:
        if not source.get("script"):
            raise RuntimeError("X user_tweets mode requires the x-crawler wrapper script")
        script = self._script_path(source.get("script") or DEFAULT_X_SCRIPT, base_dir)
        mode = source.get("mode", "search")
        limit = int(source.get("limit", 20))
        output_path = raw_dir / f"{safe_slug(source['id'])}.jsonl"
        cmd = [sys.executable, str(script)] if str(script).endswith(".py") else [str(script)]

        if mode == "search":
            query = source["query"]
            cmd.extend(["search", query, "--limit", str(limit), "--format", "jsonl", "--output", str(output_path)])
        elif mode == "user_tweets":
            username = source["username"]
            cmd.extend(["user-tweets", username, "--limit", str(limit), "--format", "jsonl", "--output", str(output_path)])
            if source.get("include_replies"):
                cmd.append("--replies")
        elif mode == "tweet":
            tweet_id = str(source["tweet_id"])
            cmd.extend(["tweet", tweet_id, "--format", "jsonl", "--output", str(output_path)])
        else:
            raise ValueError(f"Unsupported x mode for {source['id']}: {mode}")

        if source.get("proxy"):
            cmd.extend(["--proxy", source["proxy"]])
        if source.get("debug"):
            cmd.append("--debug")
        return cmd, output_path

    def _script_path(self, script: str, base_dir: Path) -> Path:
        script_path = Path(script).expanduser()
        if script_path.is_absolute():
            return script_path
        return (base_dir / script_path).resolve()

    def _output_from_stdout(self, stdout: str) -> Path | None:
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            output = payload.get("output")
            if output:
                return Path(output)
        return None

    def _result_from_docs(
        self,
        source: dict[str, Any],
        context: AdapterContext,
        docs: list[dict[str, Any]],
        artifacts: list[str],
        planned_commands: list[list[str]],
    ) -> AdapterResult:
        docs = self._filter_docs(source, docs)
        items = [self._normalize_tweet(source, context, doc) for doc in docs]
        reused = sum(
            ((item.get("raw_payload") or {}).get("processing_ledger") or {}).get("media") == "reused"
            for item in items
        )
        return AdapterResult(
            source_id=source["id"],
            source_type=self.source_type,
            items=items,
            artifacts=artifacts,
            stats={"mode": source.get("mode", "search"), "raw_count": len(docs), "normalized_count": len(items),
                   "reused_processed_items": reused,
                   "snapshot_latest": max((str((doc or {}).get("date") or (doc or {}).get("created_at") or "") for doc in docs), default=None),
                   "collected_at": context.collected_at},
            planned_commands=planned_commands,
        )

    def _filter_docs(self, source: dict[str, Any], docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if source.get("mode") != "user_tweets" or source.get("allow_author_mismatch"):
            return docs
        expected = str(source.get("username") or "").lstrip("@").lower()
        if not expected:
            return docs
        return [doc for doc in docs if self._doc_username(doc).lower() == expected]

    def _doc_username(self, data: dict[str, Any]) -> str:
        user = data.get("user") or {}
        return str(user.get("username") or data.get("username") or "")

    def _normalize_tweet(self, source: dict[str, Any], context: AdapterContext, data: dict[str, Any]) -> dict[str, Any]:
        user = data.get("user") or {}
        username = user.get("username") or data.get("username")
        display_name = user.get("displayname") or data.get("displayname")
        description = (
            user.get("rawDescription")
            or user.get("description")
            or data.get("rawDescription")
            or data.get("description")
        )
        tweet_id = data.get("id_str") or data.get("id")
        url = data.get("url")
        if not url and tweet_id and username:
            url = f"https://x.com/{username}/status/{tweet_id}"
        if not url and username:
            url = f"https://x.com/{username}"

        parent_id = data.get("inReplyToTweetIdStr") or data.get("inReplyToTweetId")
        thread_id = data.get("conversationIdStr") or data.get("conversationId") or parent_id
        is_profile_like = not tweet_id and bool(username or description)
        text = self._clean_tweet_text(data.get("rawContent") or data.get("content") or data.get("text") or description, username)
        links = data.get("links") or []
        media = data.get("media") or {}

        previous = context.processed_item(source["id"], str(tweet_id)) if tweet_id and context.processed_item else None
        previous_images = (((previous or {}).get("raw_payload") or {}).get("media") or {}).get("static_images") or []
        reusable_images = [image for image in previous_images if self._saved_image_exists(image)]
        unchanged = bool(previous) and str(((previous.get("content") or {}).get("text") or "")) == text

        static_images: list[dict[str, Any]] = []
        reused_media = False
        if unchanged and len(reusable_images) == len(x_image_candidates(media)):
            static_images = reusable_images
            reused_media = True
        elif tweet_id:
            static_images = download_static_images(
                x_image_candidates(media),
                media_root=context.base_dir / "data" / "media",
                source_id=source["id"],
                external_id=str(tweet_id),
                timeout_seconds=min(context.timeout_seconds, 60),
            )
        if static_images:
            media = dict(media) if isinstance(media, dict) else {}
            media["static_images"] = static_images

        return build_information_item(
            source_type=self.source_type,
            source_id=source["id"],
            source_name=source.get("name") or source.get("query") or username or source["id"],
            collector="x-crawler",
            adapter_version=self.adapter_version,
            tags=source.get("tags", []),
            external_id=str(tweet_id) if tweet_id else (f"profile:{username}" if username else None),
            external_url=url,
            title=f"X profile: {display_name or username}" if is_profile_like else None,
            content_text=text,
            language=data.get("lang"),
            author={
                "external_id": str(user.get("id_str") or user.get("id") or "") or None,
                "handle": username,
                "display_name": display_name,
                "profile_url": f"https://x.com/{username}" if username else None,
                "metadata": {
                    "description": description,
                    "followers_count": user.get("followersCount") or data.get("followers_count"),
                    "following_count": user.get("friendsCount") or data.get("following_count"),
                    "statuses_count": user.get("statusesCount") or data.get("statuses_count"),
                    "verified": user.get("verified") if "verified" in user else data.get("verified"),
                    "blue": user.get("blue") if "blue" in user else data.get("blue"),
                    "location": user.get("location") or data.get("location"),
                },
            },
            created_at=data.get("date") or data.get("created_at"),
            collected_at=context.collected_at,
            parent_external_id=str(parent_id) if parent_id else None,
            thread_external_id=str(thread_id) if thread_id else None,
            is_reply=bool(parent_id),
            is_repost=bool(data.get("retweetedTweet") or data.get("retweetedTweetId")),
            is_quote=bool(data.get("quotedTweet") or data.get("quotedTweetId")),
            metrics={
                "like_count": data.get("likeCount") or data.get("like_count"),
                "reply_count": data.get("replyCount") or data.get("reply_count"),
                "repost_count": data.get("retweetCount") or data.get("retweet_count"),
                "quote_count": data.get("quoteCount") or data.get("quote_count"),
                "bookmark_count": data.get("bookmarkedCount") or data.get("bookmark_count"),
                "view_count": data.get("viewCount") or data.get("view_count"),
            },
            raw_payload={
                "tweet": data,
                "links": links,
                "media": media,
                "source_config_id": source["id"],
                "processing_ledger": {
                    "status": "unchanged" if unchanged else ("changed" if previous else "new"),
                    "media": "reused" if reused_media else "refreshed",
                    "ledger_item_id": ((previous or {}).get("ingestion") or {}).get("ledger_item_id"),
                },
            },
        )

    @staticmethod
    def _saved_image_exists(image: dict[str, Any]) -> bool:
        path = Path(str(image.get("local_path") or ""))
        try:
            return path.is_file() and path.stat().st_size == int(image.get("bytes") or 0) > 0
        except (OSError, TypeError, ValueError):
            return False

    @staticmethod
    def _clean_tweet_text(value: Any, username: Any = None) -> str:
        """Keep tweet body while removing X chrome accidentally captured by snapshots."""
        if value is None:
            return ""
        text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return ""
        lines = [line.strip() for line in text.split("\n")]
        handle = str(username or "").lstrip("@").lower()
        # Browser accessibility snapshots commonly prepend author/handle/time.
        while lines and (not lines[0] or lines[0] in {"·", "•"}):
            lines.pop(0)
        # Display name is immediately followed by the handle in accessibility text.
        if len(lines) >= 2 and lines[1].startswith("@") and (not handle or lines[1][1:].lower() == handle):
            lines.pop(0)
        if lines and handle and lines[0].lstrip("@").lower() == handle:
            lines.pop(0)
        if lines and lines[0].startswith("@") and (not handle or lines[0][1:].lower() == handle):
            lines.pop(0)
        if lines and lines[0] in {"·", "•"}:
            lines.pop(0)
        if lines and re.fullmatch(r"(?:·|•)?\s*(?:\d+\s*(?:秒|分|小时|天|周|月|年)|just now|\d+[smhd])", lines[0], re.I):
            lines.pop(0)
        # Remove trailing engagement counters (reply/repost/like/view/bookmark).
        while lines and re.fullmatch(r"[\d,.]+[万亿kKmMbB]?", lines[-1]):
            lines.pop()
        return "\n".join(lines).strip()
