"""One-time reversible isolation of unverified Panyi assets; never copies credentials."""
import json, sqlite3, time, shutil, fcntl
from pathlib import Path
from panyi_backfill import ROOT, DB, SID, SINCE, STATE, inventory, is_verified_complete, write, backup

def main():
    with (ROOT/'data/panyi_backfill.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        folder=ROOT/'runs'/('panyi_old_assets_'+str(time.time_ns()))
        with sqlite3.connect(DB) as db:
            backup(db,folder)
            ids={aid for aid,raw in db.execute('SELECT external_id,raw_json FROM information_items WHERE source_id=? AND created_at>=?',(SID,SINCE)) if aid in inventory() and not is_verified_complete(json.loads(raw))}
        state=json.loads(STATE.read_text())
        write(folder/'previous_state.json',state)
        # Move only known canonical assets for the exact target IDs; historical
        # raw exports remain audit evidence but fresh batches cannot read them.
        targets=[]
        for aid in sorted(ids):
            targets.extend([ROOT/f'data/douyin_metadata/{aid}_data.json',ROOT/f'data/whisper/{aid}.json',ROOT/f'data/whisper/prepared_audio/{aid}_speech_audio.m4a',ROOT/f'data/douyin_media/{aid}'])
        audit=[]
        for path in targets:
            if not path.exists():continue
            dest=folder/'assets'/path.relative_to(ROOT/'data')
            dest.parent.mkdir(parents=True,exist_ok=True)
            audit.append({'from':str(path),'to':str(dest)})
            write(folder/'moves.json',audit)
            shutil.move(str(path),str(dest))
        state.pop('pending_batch',None)
        state.update(force_fresh=True,completed=False,fresh_target_ids=sorted(ids),old_assets_archive=str(folder))
        write(STATE,state)
        print(json.dumps({'target_count':len(ids),'moved_paths':len(audit),'archive':str(folder)},ensure_ascii=False))

if __name__=='__main__':main()
