from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import urllib.request
import urllib.error
import wave
import os
from pathlib import Path
from typing import Any

import numpy as np
from mlx_whisper import transcribe


MODEL = "mlx-community/whisper-large-v3-turbo"
INITIAL_PROMPT_TEMPLATE = (
    "以下是{author_name}的中文财经视频，涉及A股、美股、上市公司、财报、政策、AI、芯片、"
    "存储、液冷、光通信、房地产、利率与成交量。请准确保留公司名、英文缩写、百分比和数字。"
)


def load_metadata(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def audio_urls(metadata: dict[str, Any]) -> list[str]:
    """Return final playback audio URLs, never the separate background-music asset."""
    candidates: list[tuple[int, str]] = []
    for rendition in (metadata.get("video") or {}).get("bit_rate_audio") or []:
        audio_meta = rendition.get("audio_meta") or {}
        bitrate = int(audio_meta.get("bitrate") or rendition.get("bit_rate") or 0)
        # Douyin returns url_list as either a list or a named mapping.  Iterating
        # a mapping yields the keys ("main_url", "backup_url") and silently
        # makes the downloader fall back to the MP4, which can contain the
        # wrong/muted track.  Always extract the URL values themselves.
        url_list = audio_meta.get("url_list") or []
        urls = url_list.values() if isinstance(url_list, dict) else url_list
        for url in urls:
            if url:
                candidates.append((bitrate, str(url)))
    candidates.sort(reverse=True)
    return list(dict.fromkeys(url for _, url in candidates))


def download_playback_audio(metadata: dict[str, Any], destination: Path, stop_on_http_error: bool = False) -> Path | None:
    if destination.exists() and destination.stat().st_size > 1024:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    for url in audio_urls(metadata):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.douyin.com/"},
        )
        temporary = destination.with_suffix(destination.suffix + ".part")
        try:
            with urllib.request.urlopen(request, timeout=30) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if temporary.stat().st_size <= 1024:
                temporary.unlink(missing_ok=True)
                continue
            temporary.replace(destination)
            return destination
        except urllib.error.HTTPError as exc:
            temporary.unlink(missing_ok=True)
            if stop_on_http_error:
                raise RuntimeError(f"audio_http_error status={exc.code}; Retry-After={exc.headers.get('Retry-After', '')}") from None
        except Exception:
            temporary.unlink(missing_ok=True)
    return None


def speech_source(metadata_path: Path, metadata: dict[str, Any], prepared_dir: Path, media_root: Path | None = None, stop_on_http_error: bool = False) -> Path:
    aweme_id = str(metadata.get("aweme_id") or "")
    if not aweme_id:
        raise ValueError(f"missing aweme_id in {metadata_path}")
    playback_audio = download_playback_audio(metadata, prepared_dir / f"{aweme_id}_speech_audio.m4a", stop_on_http_error)
    if playback_audio:
        return playback_audio
    # Older metadata often has no bit_rate_audio field. In that case use the
    # already downloaded MP4 and extract its embedded speech track locally.
    # This is deliberately after the direct-audio attempt, so we never prefer
    # a background music asset over the video's own narration.
    if media_root:
        candidates = list((media_root / aweme_id).rglob("*.mp4")) + list(media_root.rglob(f"{aweme_id}*.mp4"))
        if candidates:
            video = candidates[0]
            destination = prepared_dir / f"{aweme_id}_speech_audio.m4a"
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(["/usr/bin/swift", str(Path(__file__).with_name("extract_audio.swift")), str(video), str(destination)], check=True, timeout=120)
                if destination.exists() and destination.stat().st_size > 1024:
                    return destination
            except Exception:
                destination.unlink(missing_ok=True)
    raise FileNotFoundError(f"{aweme_id}: no audio track and no downloaded video fallback")


def pcm_audio(path: Path) -> np.ndarray:
    """Decode with macOS AudioToolbox so mlx-whisper does not require ffmpeg."""
    with tempfile.TemporaryDirectory(prefix="douyin-asr-") as temp_dir:
        wav_path = Path(temp_dir) / "speech.wav"
        source = path
        subprocess.run(
            ["/usr/bin/afconvert", str(source), str(wav_path), "-f", "WAVE", "-d", "LEI16@16000", "-c", "1"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        with wave.open(str(wav_path), "rb") as wav_file:
            if wav_file.getnchannels() != 1 or wav_file.getframerate() != 16000 or wav_file.getsampwidth() != 2:
                raise ValueError(f"unexpected decoded audio format for {path}")
            samples = np.frombuffer(wav_file.readframes(wav_file.getnframes()), dtype="<i2")
    return samples.astype(np.float32) / 32768.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe final playback audio from Douyin metadata.")
    parser.add_argument("--metadata-root", dest="metadata_root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--prepared-dir", type=Path)
    parser.add_argument("--media-root", type=Path, help="Downloaded Douyin video root used when metadata has no audio URL")
    parser.add_argument("--author-name", default="久韭究财")
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--stop-on-http-error", action="store_true", help="Stop the batch at the first audio HTTP error; no URL fallback")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    prepared_dir = args.prepared_dir or args.output_dir / "prepared_audio"

    requested_ids = set(args.ids or [])
    jobs: list[tuple[Path, dict[str, Any]]] = []
    metadata_paths = list(args.metadata_root.rglob("*_data.json")) + list(args.metadata_root.rglob("*.mp4.metadata.json"))
    for metadata_path in sorted(set(metadata_paths)):
        metadata = load_metadata(metadata_path)
        aweme_id = str(metadata.get("aweme_id") or "")
        if aweme_id and (not requested_ids or aweme_id in requested_ids):
            jobs.append((metadata_path, metadata))

    for index, (metadata_path, metadata) in enumerate(jobs, 1):
        aweme_id = str(metadata["aweme_id"])
        output = args.output_dir / f"{aweme_id}.json"
        if output.exists() and not args.force:
            print(f"[{index}/{len(jobs)}] skip {aweme_id}", flush=True)
            continue
        try:
            source = speech_source(metadata_path, metadata, prepared_dir, args.media_root, args.stop_on_http_error)
        except FileNotFoundError as exc:
            # A missing playback track is an expected per-video condition
            # (e.g. older/private cards).  Leave it for the title-only
            # fallback in prepare_douyin_ingestion instead of aborting the
            # entire batch and hiding transcripts for later videos.
            print(f"[{index}/{len(jobs)}] skip {aweme_id}: {exc}", flush=True)
            continue
        print(f"[{index}/{len(jobs)}] transcribe {aweme_id}: {source.name}", flush=True)
        result = transcribe(pcm_audio(source), path_or_hf_repo=MODEL, language="zh", verbose=False,
            condition_on_previous_text=True, initial_prompt=INITIAL_PROMPT_TEMPLATE.format(author_name=args.author_name))
        result["speech_source"] = str(source.resolve())
        result["transcription_method"] = "mlx_whisper"
        output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        print(
            f"[{index}/{len(jobs)}] saved {output.name} "
            f"segments={len(result.get('segments') or [])} chars={len(result.get('text') or '')}",
            flush=True,
        )


if __name__ == "__main__":
    main()
