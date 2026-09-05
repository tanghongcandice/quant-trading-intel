"""Hold an OS-released lock across the complete daily collection process."""
import fcntl
import os
from pathlib import Path

root = Path(__file__).resolve().parents[1]
lock = (root / 'data' / 'daily_collection.lock').open('a')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit('Collection already running; duplicate start refused (no sources collected).')
os.set_inheritable(lock.fileno(), True)
os.environ['QUANT_COLLECTION_LOCKED'] = '1'
os.execv('/bin/bash', ['bash', str(root / 'scripts/run_daily_collection.sh')])
