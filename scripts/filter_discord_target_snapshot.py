import json
from pathlib import Path
p = Path(__file__).resolve().parents[1] / 'data/browser_sessions/discord_haochi_daqu.json'
d = json.loads(p.read_text())
a = '好吃好吃啊～～～～～～～～～～～～～'
msgs = [m for m in d.get('messages', []) if (m.get('author') or {}).get('name') == a]
p.write_text(json.dumps({'messages': msgs}, ensure_ascii=False, indent=2))
print({'target_messages': len(msgs)})
