#!/usr/bin/env python3
"""Connect Douyin asset download, audio extraction, and Whisper ASR.

Audio URL is attempted first. If unavailable, the downloaded MP4 is used as
the source and its embedded audio is extracted before transcription.
"""
import argparse, subprocess, sys
from pathlib import Path

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--metadata-root', type=Path, required=True)
    p.add_argument('--media-root', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--snapshot', type=Path, help='Browser profile snapshot; download missing videos before ASR')
    p.add_argument('--whisper-dir', type=Path, help='Prepared audio directory (defaults to output-dir)')
    p.add_argument('--ids', nargs='*')
    p.add_argument('--force', action='store_true')
    a = p.parse_args()
    if a.snapshot:
        enrich = [sys.executable, str(Path(__file__).with_name('enrich_douyin_audio.py')),
                  '--snapshot', str(a.snapshot), '--metadata-root', str(a.metadata_root),
                  '--whisper-dir', str(a.whisper_dir or a.output_dir), '--media-dir', str(a.media_root)]
        if a.ids: enrich += ['--ids', *a.ids]
        rc = subprocess.call(enrich)
        if rc: raise SystemExit(rc)
    cmd = [sys.executable, str(Path(__file__).with_name('transcribe_douyin_batch.py')),
           '--metadata-root', str(a.metadata_root), '--media-root', str(a.media_root),
           '--output-dir', str(a.output_dir)]
    if a.whisper_dir: cmd += ['--prepared-dir', str(a.whisper_dir / 'prepared_audio')]
    cmd += ['--media-root', str(a.media_root)]
    if a.ids: cmd += ['--ids', *a.ids]
    if a.force: cmd.append('--force')
    raise SystemExit(subprocess.call(cmd))

if __name__ == '__main__':
    main()
