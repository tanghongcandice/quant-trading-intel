"""Final-store Discord author and cross-post checks, shared by every importer."""
import json
import re
import unicodedata
from datetime import datetime

TIANYI = 'discord_tianyi_edgerunner_trades'
SOURCES = {TIANYI, 'discord_club500_edgerunner_messages', 'discord_club500_fm_trade_chat'}
TARGET = '1089568152251273228'
NAMES = {'edgerunner', 'edgerunner17888', 'edgerunner (magnificent balance)', 'edgerunner (great balance sheet)'}

def sid(item):
    return item.get('source', {}).get('id')

def target(item):
    a = item.get('author') or {}
    ident = a.get('external_id') or ((item.get('raw_payload', {}).get('discord') or {}).get('author') or {}).get('id')
    if ident:
        return str(ident) == TARGET
    return any(str(a.get(k) or '').strip().casefold() in NAMES for k in ('handle', 'display_name'))

def normalize(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text or '')).strip().casefold()

def body(item):
    p = item.get('raw_payload') or {}
    return str((p.get('discord') or {}).get('content') or item.get('content', {}).get('text') or '')

def media(item):
    p = item.get('raw_payload') or {}
    hashes = {m['sha256'] for m in (p.get('media') or {}).get('static_images', []) if m.get('sha256')}
    # Signed URLs are unsuitable identifiers. Attachment snowflakes are stable.
    attachments = (p.get('discord') or {}).get('attachments') or []
    ids = {str(a.get('id')) for a in attachments if a.get('id')}
    return hashes, ids

def duplicate(a, b):
    if sid(a) not in SOURCES or sid(b) not in SOURCES or sid(a) == sid(b) or not target(a) or not target(b):
        return False
    try:
        dates = [datetime.fromisoformat(i['timestamps']['created_at'].replace('Z', '+00:00')) for i in (a, b)]
        if abs((dates[0] - dates[1]).total_seconds()) > 120:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    ra, rb = a.get('relations') or {}, b.get('relations') or {}
    if bool(ra.get('is_reply')) != bool(rb.get('is_reply')):
        return False
    if ra.get('is_reply'):
        contexts = [(i.get('raw_payload') or {}).get('reply_context') or {} for i in (a, b)]
        texts = [normalize(c.get('content') or c.get('text')) for c in contexts]
        if not all(texts) or texts[0] != texts[1]:
            return False
    ma, mb = media(a), media(b)
    if ma[0] and mb[0] and ma[0] != mb[0]:
        return False
    x, y = normalize(body(a)), normalize(body(b))
    if not x or not y:
        return bool(ma[0] and ma[0] == mb[0])
    if x == y:
        return True
    # Legacy appended Chinese translation: only whole-line suffixes, never
    # arbitrary prefixes ("sold" vs "sold half"). Keep stored English intact.
    for short, long in ((body(a), body(b)), (body(b), body(a))):
        lines = long.splitlines()
        for n in range(1, len(lines)):
            suffix = '\n'.join(lines[n:])
            if normalize('\n'.join(lines[:n])) == normalize(short) and re.search('[\u4e00-\u9fff]', suffix) and not re.search('[\u4e00-\u9fff]', short):
                return True
    return False

def enforce(conn, run_id):
    conn.execute('CREATE TABLE IF NOT EXISTS discord_guard_audit (run_id TEXT, action TEXT, item_id TEXT, kept_id TEXT, before_json TEXT)')
    rows = conn.execute("SELECT id,raw_json FROM information_items WHERE source_id IN (?,?,?)", tuple(sorted(SOURCES))).fetchall()
    items = []
    hidden = removed = 0
    for row in rows:
        item = json.loads(row['raw_json']); p = item.setdefault('raw_payload', {})
        if not target(item):
            if p.get('analysis_role') != 'reply_context_only':
                conn.execute('INSERT INTO discord_guard_audit VALUES (?,?,?,?,?)', (run_id,'non_target_context_only',row['id'],None,row['raw_json']))
                p.update(analysis_role='reply_context_only', analysis_policy={'include':False,'mode':'context_only'}, author_verification='not_verified_target')
                conn.execute('UPDATE information_items SET raw_json=? WHERE id=?',(json.dumps(item,ensure_ascii=False),row['id']))
                for table in ('item_entities','item_analysis'):
                    conn.execute(f'DELETE FROM {table} WHERE item_id=?',(row['id'],))
                hidden += 1
            continue
        items.append((row,item))
    items.sort(key=lambda pair:(sid(pair[1]) != TIANYI, pair[0]['id']))
    kept=[]
    for row,item in items:
        match=next((r for r,i in kept if duplicate(item,i)),None)
        if match is None:
            kept.append((row,item));continue
        conn.execute('INSERT INTO discord_guard_audit VALUES (?,?,?,?,?)',(run_id,'cross_source_duplicate',row['id'],match['id'],row['raw_json']))
        for table in ('item_entities','item_analysis','information_items_fts'):
            conn.execute(f'DELETE FROM {table} WHERE item_id=?',(row['id'],))
        conn.execute('DELETE FROM information_items WHERE id=?',(row['id'],));removed+=1
    return {'duplicates_removed':removed,'non_target_hidden':hidden}
