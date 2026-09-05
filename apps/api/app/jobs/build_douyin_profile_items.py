from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.jobs.repair_douyin_transcripts import (
    MODEL_NAME,
    apply_contextual_corrections,
    content_hash,
    format_whisper_segments,
)


DEFAULT_PROFILE_URL = "https://www.douyin.com/user/MS4wLjABAAAAfZSJLO6q-2SWxDS2tp2oor3lawUH4JB2TPKWOGoykXU"
DEFAULT_SOURCE_ID = "douyin_jiujiujiucai"
DEFAULT_AUTHOR_NAME = "久韭究财"
DEFAULT_AUTHOR_EXTERNAL_ID = "MS4wLjABAAAAfZSJLO6q-2SWxDS2tp2oor3lawUH4JB2TPKWOGoykXU"
MEMBER_NOTICE = "【会员专属作品｜当前仅保存标题，不下载未获授权的完整内容】"
NO_AUDIO_NOTICE = "【视频无可转录音轨｜当前仅保存标题】"
NO_SPEECH_NOTICE = "【视频未检测到可靠财经口播｜当前仅保存标题】"


def utc_iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_metadata(root: Path) -> dict[str, tuple[Path, dict]]:
    result: dict[str, tuple[Path, dict]] = {}
    for path in root.rglob("*_data.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        aweme_id = str(data.get("aweme_id") or "")
        if aweme_id:
            result[aweme_id] = (path, data)
    return result


def build_item(
    work: dict,
    metadata: dict[str, tuple[Path, dict]],
    whisper_dir: Path,
    collected_at: str,
    *,
    source_id: str,
    author_name: str,
    author_external_id: str,
    profile_url: str,
) -> dict:
    aweme_id = str(work["aweme_id"])
    title = str(work.get("title") or "").strip()
    review_only = bool(work.get("review_only"))
    no_audio = bool(work.get("no_audio"))
    no_speech = bool(work.get("no_speech"))
    created_at = utc_iso(int(aweme_id) >> 32)
    transcription: dict
    metadata_path = None
    media_path = None

    if review_only or no_audio or no_speech:
        text = MEMBER_NOTICE if review_only else (NO_AUDIO_NOTICE if no_audio else NO_SPEECH_NOTICE)
        transcription = {
            "status": (
                "member_title_only" if review_only else ("no_audio_title_only" if no_audio else "no_speech_title_only")
            ),
            "model": None,
            "text_refinement": None,
        }
    else:
        if aweme_id not in metadata:
            raise FileNotFoundError(f"missing Douyin metadata for {aweme_id}")
        metadata_path, detail = metadata[aweme_id]
        whisper_path = whisper_dir / f"{aweme_id}.json"
        if not whisper_path.exists():
            raise FileNotFoundError(f"missing Whisper result for {aweme_id}: {whisper_path}")
        whisper = json.loads(whisper_path.read_text(encoding="utf-8"))
        text, removed = format_whisper_segments(whisper)
        text, corrections = apply_contextual_corrections(title, text)
        if text.endswith("\n\n现在"):
            text = text[: -len("\n\n现在")].rstrip()
        if not text:
            raise ValueError(f"empty transcript for {aweme_id}")
        # The speech source is the independently downloaded Douyin
        # ``bit_rate_audio`` track used by Whisper.  Do not point the item at
        # ``*_music.mp3``: that is optional background music, not the spoken
        # track, and it may not exist when audio-only collection is enabled.
        speech_source = whisper.get("speech_source")
        media_path = Path(speech_source) if speech_source else None
        segments = whisper.get("segments") or []
        transcript_end = max((float(segment.get("end") or 0) for segment in segments), default=0)
        media_duration = float(detail.get("duration") or (detail.get("video") or {}).get("duration") or 0) / 1000
        # Douyin's metadata duration can include a short silent tail after the
        # independently downloaded speech track.  Treat only larger gaps as
        # an incomplete transcript; a few seconds of trailing silence is
        # expected and should not block an otherwise complete Whisper result.
        if media_duration and transcript_end < media_duration - 8:
            raise ValueError(
                f"{aweme_id}: transcript ends at {transcript_end:.2f}s before media ends at {media_duration:.2f}s"
            )
        transcription = {
            "status": "complete",
            "model": MODEL_NAME,
            "media_duration_seconds": round(media_duration, 3),
            "transcript_end_seconds": round(transcript_end, 3),
            "removed_repetitions": removed,
            "contextual_corrections": list(corrections),
            "text_refinement": {
                "method": "codex_title_and_finance_context_review",
                "reviewer": "codex",
                "preserve_numbers": True,
                "preserve_claims": True,
            },
        }

    item_id = "itm_" + hashlib.sha256(f"{source_id}:{aweme_id}".encode()).hexdigest()[:24]
    digest = content_hash(title, text)
    return {
        "schema_version": "information_item.v1",
        "id": item_id,
        "source": {
            "type": "douyin",
            "id": source_id,
            "name": f"抖音 {author_name}",
            "collector": "logged_in_profile+video-downloader+mlx-whisper-large-v3-turbo",
            "tags": ["market:cn"],
        },
        "external": {
            "id": aweme_id,
            "url": f"https://www.douyin.com/video/{aweme_id}",
            "parent_id": None,
            "thread_id": None,
        },
        "author": {
            "handle": author_name,
            "display_name": author_name,
            "external_id": author_external_id,
            "profile_url": profile_url,
            "metadata": {},
        },
        "content": {"title": title, "text": text, "html": None, "language": "zh", "hash": digest},
        "timestamps": {"created_at": created_at, "collected_at": collected_at},
        "metrics": {},
        "entities": [],
        "relations": {"is_reply": False, "is_repost": False, "is_quote": False},
        "analysis": None,
        "raw_payload": {
            "market": "cn",
            "comments_collected": False,
            "profile_snapshot": True,
            "access_label": work.get("access_label"),
            "metadata_path": str(metadata_path.resolve()) if metadata_path else None,
            "audio_path": str(media_path.resolve()) if media_path else None,
            "transcription": transcription,
            "analysis_policy": {
                "include": not (review_only or no_audio or no_speech),
                "mode": "review_only" if (review_only or no_audio or no_speech) else "analysis",
                "reason": (
                    "subscription_preview"
                    if review_only
                    else ("no_audio_track" if no_audio else ("no_reliable_finance_speech" if no_speech else None))
                ),
            },
        },
        "ingestion": {"dedupe_key": f"{source_id}:external_id:{aweme_id}"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Douyin information_item JSONL from a profile snapshot and ASR.")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--metadata-root", required=True, type=Path)
    parser.add_argument("--whisper-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-id", default=DEFAULT_SOURCE_ID)
    parser.add_argument("--author-name", default=DEFAULT_AUTHOR_NAME)
    parser.add_argument("--author-external-id", default=DEFAULT_AUTHOR_EXTERNAL_ID)
    parser.add_argument("--profile-url", default=DEFAULT_PROFILE_URL)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    metadata = load_metadata(args.metadata_root)
    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    items = [
        build_item(
            work,
            metadata,
            args.whisper_dir,
            collected_at,
            source_id=args.source_id,
            author_name=args.author_name,
            author_external_id=args.author_external_id,
            profile_url=args.profile_url,
        )
        for work in snapshot.get("works") or []
        if not work.get("pinned")
    ]
    items.sort(key=lambda item: item["timestamps"]["created_at"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "items": len(items),
                "complete": sum(item["raw_payload"]["transcription"]["status"] == "complete" for item in items),
                "review_only": sum(item["raw_payload"]["analysis_policy"]["include"] is False for item in items),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
