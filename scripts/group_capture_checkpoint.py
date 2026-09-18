"""Durable same-run rendered-DOM windows and computed group completeness.

This module never operates Chrome. CUA submits only visible message fields.
New runs must observe the page again; uncommitted prior-run ASR is not reused.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from build_douyin_group import GROUP, SOURCE, TZ, resolve_time
from browser_session_bridge import _write_atomic
from douyin_group_processing_ledger import voice_batches, reuse, _load_ledger, DEFAULT_LEDGER


def stamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamp must have a timezone')
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def signature(row):
    # Transcript text, relative time labels and viewport index are not identity.
    text = str(row.get('text') or '')
    if row.get('time'): text = text.removeprefix(row['time']).lstrip()
    if row.get('author'):
        text = text.removeprefix(row['author']).lstrip()
        text = re.sub(r'^(群主|管理员)\s*', '', text)
    return [row.get('duration') or text, row.get('author') or '',
            row.get('role') or '', row.get('message_kind') or '',
            [i.get('url', '').split('?', 1)[0] for i in row.get('images', [])]]


def alignment_shift(rows, incoming):
    """Accept only a unique contiguous overlap with a non-duration anchor.

    Positive shifts rebase saved rows into the new live index coordinate system.
    Duration-only repetitions are deliberately insufficient evidence for rebasing.
    """
    common = set(rows) & set(incoming)
    if common and all(signature(rows[i]) == signature(incoming[i]) for i in common):
        return 0
    candidates = set()
    for old_i, old in rows.items():
        if old.get('duration') or not old.get('text'):
            continue
        for new_i, new in incoming.items():
            if signature(old) == signature(new):
                candidates.add(new_i - old_i)
    valid = []
    for shift in candidates:
        if shift < 0:
            continue  # deletion/reordering requires explicit review
        overlap = sorted(i for i in incoming if i - shift in rows)
        if len(overlap) < 3 or overlap != list(range(overlap[0], overlap[-1] + 1)):
            continue
        if all(signature(rows[i-shift]) == signature(incoming[i]) for i in overlap):
            valid.append(shift)
    if len(valid) != 1:
        if not common and not candidates:
            raise ValueError('Window has no overlap; return to previous visible boundary')
        raise ValueError('DOM indexes shifted or message changed; ambiguous overlap, return to a text/time boundary')
    return valid[0]


def merge_windows(windows):
    rows = {}
    for window in windows:
        incoming = {int(row['index']): copy.deepcopy(row) for row in window['messages']}
        if len(incoming) != len(window['messages']):
            raise ValueError('Duplicate DOM indexes')
        if rows:
            shift = alignment_shift(rows, incoming)
            if shift:
                rows = {i + shift: dict(row, index=i + shift) for i, row in rows.items()}
        for index, row in incoming.items():
            if index in rows and not row.get('voice'):
                row['voice'] = rows[index].get('voice', '')
            if index in rows and not row.get('shared_video') and rows[index].get('shared_video'):
                row['shared_video'] = rows[index]['shared_video']
            if row.get('time'):
                row['resolved_time'] = resolve_time(row['time'], stamp(window['captured_at']).astimezone(TZ))
            rows[index] = row
    return sorted(rows.values(), key=lambda r: int(r['index']))


def cursor(root):
    db = root / 'data/quant_intel.sqlite'
    if not db.exists():
        return None
    with sqlite3.connect(db) as conn:
        row = conn.execute('SELECT last_successful_created_at FROM source_cursors WHERE source_id=?', (SOURCE,)).fetchone()
    return row[0] if row else None


def completeness(payload, final_cursor):
    rows = payload.get('messages') or []
    indexes = sorted(int(row['index']) for row in rows)
    errors = []
    if not indexes or indexes[0] != 0 or indexes != list(range(indexes[-1] + 1)):
        errors.append('Latest index zero and contiguous DOM coverage required')
    times = [stamp(row['resolved_time']) for row in rows if row.get('resolved_time')]
    cutoff = stamp(final_cursor) - timedelta(hours=2) if final_cursor else None
    if cutoff is None:
        errors.append('No final-store cursor; initial capture requires explicit historical boundary review')
    elif not times or min(times) > cutoff:
        errors.append('Two-hour final-store cursor overlap not reached')
    # Oldest loaded row must establish an observed time and break inherited
    # speech. Otherwise an offscreen prefix could be missing.
    if rows and (not rows[-1].get('resolved_time') or rows[-1].get('duration')):
        errors.append('Oldest boundary is an open/undated batch; scroll farther')
    pending = [index for batch in voice_batches(payload)
               for index, voice in zip(batch['indexes'], batch['voices']) if not voice]
    if pending: errors.append('Pending native voice transcription')
    covered = {int(index) for batch in voice_batches(payload) for index in batch['indexes']}
    known_author, role = False, None
    for row in reversed(rows):
        if row.get('message_kind') == 'system_notice' or (not row.get('author') and '加入了群聊' in str(row.get('text') or '')):
            known_author, role = False, None
            continue
        if row.get('author'):
            known_author, role = True, row.get('role')
        if row.get('duration') and (not known_author or (role in {'群主', '管理员'} and int(row['index']) not in covered)):
            errors.append('Voice context lacks verified author/time boundary')
        if role in {'群主', '管理员'} and row.get('message_kind') == 'video_share' and not row.get('shared_video'):
            errors.append('Unresolved video share; retain checkpoint for review')
    return {'errors': errors, 'pending_voice_indexes': pending,
            'pending_voice_count': len(pending), 'cursor_cutoff': cutoff.isoformat() if cutoff else None,
            'earliest_checked': min(times).isoformat() if times else None}


def checkpoint(root, run_id, window):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', run_id): raise ValueError('Invalid run ID')
    if window.get('group_name') != GROUP: raise ValueError('Wrong group')
    if not 0 <= (datetime.now(timezone.utc)-stamp(window['captured_at'])).total_seconds() <= 120:
        raise ValueError('DOM window is stale/future-dated')
    folder = root / 'runs' / run_id
    folder.mkdir(parents=True, exist_ok=True)
    windows_path = folder / 'group_windows'
    windows_path.mkdir(exist_ok=True)
    files = sorted(windows_path.glob('*.json'))
    windows = [json.loads(f.read_text()) for f in files]
    # Persist failed windows separately too; never silently discard shift evidence.
    try:
        rows = merge_windows(windows + [window])
    except ValueError:
        _write_atomic(folder / 'group_rejected_window.json', window)
        raise
    path = windows_path / f'{len(files):06d}.json'
    _write_atomic(path, window)
    windows.append(window)
    final_cursor = cursor(root)
    payload = {'group_name': GROUP, 'captured_at': window['captured_at'],
               'history_complete': False, 'messages': rows, 'voice_paragraph_starts': []}
    # Every operation starts from observed windows; only final DB can supply
    # missing cross-run transcript segments.
    reused = reuse(payload, _load_ledger(root / DEFAULT_LEDGER), root / 'data/quant_intel.sqlite')
    result = completeness(payload, final_cursor)
    latest_windows = [w for w in windows if w.get('at_latest') and any(int(r['index']) == 0 for r in w['messages'])]
    anchor = lambda w: next(signature(r) for r in w['messages'] if int(r['index']) == 0)
    stable = len(latest_windows) >= 2 and anchor(latest_windows[-2]) == anchor(latest_windows[-1])
    # Last window must return to the latest end after overlap and transcription.
    stable = stable and window.get('at_latest') is True
    if not stable: result['errors'].append('Recheck latest anchor after overlap/transcription')
    payload['collection_evidence'] = {'run_id':run_id, 'version':2, 'latest_checked':stable,
        'overlap_covered':not any('overlap' in e or 'coverage' in e or 'boundary' in e for e in result['errors']),
        'pending_voice_count':result['pending_voice_count'], 'final_db_cursor':final_cursor,
        'earliest_checked':result['earliest_checked'],
        'windows':[{'file':f'group_windows/{i:06d}.json','sha256':digest(w)} for i,w in enumerate(windows)]}
    _write_atomic(folder / 'group_checkpoint.json', payload)
    from group_retry_queue import sync
    retry = sync(root, payload, run_id)
    result['pending_video_indexes'] = retry['pending_video_indexes']
    result['retry_queue'] = retry
    result.update(reused, run_id=run_id, raw_messages=len(rows), ready=not result['errors'])
    _write_atomic(folder / 'group_checkpoint_status.json', result)
    return result


def validate_capture(payload, root, run_id, allow_partial=False, historical=False):
    ev = payload.get('collection_evidence') or {}
    if ev.get('version') != 2 or ev.get('run_id') != run_id:
        raise ValueError('A version-2 same-run DOM checkpoint is required')
    if payload.get('group_name') != GROUP: raise ValueError('Wrong group')
    if not historical and not 0 <= (datetime.now(timezone.utc)-stamp(payload['captured_at'])).total_seconds() <= 7200:
        raise ValueError('Capture stale or future-dated')
    windows = []
    for entry in ev.get('windows') or []:
        if not re.fullmatch(r'group_windows/\d{6}\.json', entry['file']):
            raise ValueError('Invalid window evidence path')
        window = json.loads((root / 'runs' / run_id / entry['file']).read_text())
        if window.get('group_name') != GROUP or digest(window) != entry['sha256']:
            raise ValueError('DOM window evidence mismatch')
        windows.append(window)
    if len(windows) < 2: raise ValueError('Two latest-end observations required')
    expected = merge_windows(windows)
    probe = {'group_name': GROUP, 'captured_at': payload['captured_at'], 'messages': expected}
    reuse(probe, _load_ledger(root / DEFAULT_LEDGER), root / 'data/quant_intel.sqlite')
    actual = payload.get('messages') or []
    if [(r['index'],signature(r),r.get('resolved_time')) for r in actual] != [(r['index'],signature(r),r.get('resolved_time')) for r in expected]:
        raise ValueError('Capture differs from observed DOM windows')
    if [r.get('voice','') for r in actual] != [r.get('voice','') for r in expected]:
        raise ValueError('Transcript lacks observed DOM or final-store reuse provenance')
    if [r.get('shared_video') for r in actual] != [r.get('shared_video') for r in expected]:
        raise ValueError('Video link lacks observed window provenance')
    if payload['captured_at'] != windows[-1]['captured_at']:
        raise ValueError('Capture timestamp differs from final observed window')
    last = windows[-1]
    anchors = lambda w: [signature(r) for r in w['messages'] if int(r['index']) == 0]
    latest = [w for w in windows if w.get('at_latest') and anchors(w)]
    latest_verified = len(latest) >= 2 and last.get('at_latest') and anchors(latest[-2]) == anchors(last)
    if not latest_verified and not allow_partial:
        raise ValueError('Latest anchor changed or not rechecked')
    # Use the earlier, captured cursor as the required baseline. A concurrent
    # import may move it forward, but never justify less overlap than observed.
    baseline = ev.get('final_db_cursor')
    current = cursor(root)
    if not baseline or (current and stamp(baseline) > stamp(current)):
        raise ValueError('Invalid final-store cursor baseline')
    result = completeness(payload, baseline)
    if not latest_verified:
        result['errors'].append('Recheck latest anchor after overlap/transcription')
    if result['errors'] and not allow_partial: raise ValueError('; '.join(result['errors']))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--window', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(checkpoint(args.root, args.run_id, json.loads(args.window.read_text())), ensure_ascii=False))


if __name__ == '__main__': main()
