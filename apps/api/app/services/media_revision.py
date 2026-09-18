"""Attach verified missing static media without changing a message's content."""
import hashlib
import json
from pathlib import Path


def update_static_media(conn, item, run_id):
    payload = item.get('raw_payload') or {}
    if not payload.get('static_media_recovery'):
        return False
    row = conn.execute('SELECT raw_json FROM information_items WHERE id=?', (item['id'],)).fetchone()
    if not row:
        return False
    before = row['raw_json']; old = json.loads(before)
    for key in ('source', 'external', 'content', 'author', 'timestamps'):
        if old.get(key) != item.get(key):
            raise ValueError('Static media recovery must preserve message identity and body')
    old_payload = old.get('raw_payload') or {}
    known = {m.get('sha256') for m in (old_payload.get('media') or {}).get('static_images', [])}
    attachments = (old_payload.get('discord') or {}).get('attachments') or []
    allowed = {a.get('url') for a in attachments}
    added = []
    for media in (payload.get('media') or {}).get('static_images', []):
        if media.get('sha256') in known:
            continue
        path = Path(media['local_path']).resolve()
        media_root = Path(__file__).resolve().parents[4] / 'data' / 'media'
        relative = path.relative_to(media_root.resolve()).as_posix()
        data = path.read_bytes()
        if (media.get('source_url') not in allowed or not data
                or hashlib.sha256(data).hexdigest() != media.get('sha256')
                or len(data) != media.get('bytes')
                or media.get('api_url') != '/media/' + relative):
            raise ValueError('Static media evidence does not match saved attachment')
        added.append(media); known.add(media['sha256'])
    if not added:
        return False
    old_payload.setdefault('media', {}).setdefault('static_images', []).extend(added)
    old_payload['static_media_recovery'] = payload['static_media_recovery']
    old['raw_payload'] = old_payload
    conn.execute('CREATE TABLE IF NOT EXISTS media_revision_audit (run_id TEXT, item_id TEXT, before_json TEXT, after_json TEXT)')
    after = json.dumps(old, ensure_ascii=False, sort_keys=True)
    conn.execute('INSERT INTO media_revision_audit VALUES (?,?,?,?)', (run_id, item['id'], before, after))
    conn.execute('UPDATE information_items SET raw_json=? WHERE id=?', (after, item['id']))
    return True
