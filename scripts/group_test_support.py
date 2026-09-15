import json, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from group_capture_checkpoint import checkpoint
from build_douyin_group import GROUP, SOURCE

def setup(root):
    db = root / 'data/quant_intel.sqlite'
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as conn:
        conn.executescript((Path(__file__).resolve().parents[1]/'packages/shared/database_schema.sql').read_text())
        conn.execute('CREATE TABLE IF NOT EXISTS source_cursors(source_id TEXT PRIMARY KEY,last_successful_created_at TEXT,last_successful_external_id TEXT,updated_at TEXT,run_id TEXT)')
        conn.execute('INSERT INTO source_cursors VALUES(?,?,?,?,?)',(SOURCE,'2026-09-15T11:37:00+08:00','old','now','old'))
    return db

def window():
    return {'group_name':GROUP,'captured_at':datetime.now(timezone.utc).isoformat(),'at_latest':True,'messages':[
        {'index':0,'text':'8"','duration':'8"','voice':'第二段。'},
        {'index':1,'text':'09/15 11:35\n宇菠萝\n管理员\n3"','time':'09/15 11:35','author':'宇菠萝','role':'管理员',
         'images':[{'url':'https://p3.douyinpic.com/img/aweme-avatar/a.webp'}],'duration':'3"','voice':'第一段。'},
        {'index':2,'text':'09/15 08:00\n新人 加入了群聊','time':'09/15 08:00','message_kind':'system_notice'}]}

def ready(root, run='test'):
    w=window()
    checkpoint(root,run,w)
    checkpoint(root,run,w)
    return json.loads((root/'runs'/run/'group_checkpoint.json').read_text())
