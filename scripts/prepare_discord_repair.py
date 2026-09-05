"""Stage a complete verified capture without discarding gaps behind a cursor."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'packages/ingestion_scheduler/src'))
from ingestion_scheduler.adapters.base import AdapterContext
from ingestion_scheduler.adapters.discord import DiscordAdapter
from ingestion_scheduler.utils import sha256_text

folder = root / 'runs/discord_repair_20260905'
payload = json.loads((folder / 'verified_raw.json').read_text())
assert payload['stop_reason'] == 'cutoff_reached', 'Incomplete capture must not advance import cursor'
source = next(s for s in json.loads((root / 'configs/ingestion/premarket.template.json').read_text())['sources'] if s['id'] == 'discord_haochi_daqu')
ctx = AdapterContext(base_dir=root,run_id=folder.name,run_dir=folder,raw_dir=folder,
    collected_at=datetime.now(timezone.utc).isoformat(),dry_run=False,timeout_seconds=12)
docs = DiscordAdapter().normalize_docs(source, ctx, payload['messages']).items
for item in docs:
    key = 'discord:external_id:' + item['external']['id']
    item['id'] = 'itm_' + sha256_text(key)[:24]
    item.setdefault('ingestion', {})['dedupe_key'] = key
(folder / 'verified_items.jsonl').write_text(''.join(json.dumps(i,ensure_ascii=False) + '\n' for i in docs))
print(json.dumps({'staged':len(docs), 'target':sum((i.get('raw_payload')or{}).get('analysis_role')!='reply_context_only' for i in docs)}))
