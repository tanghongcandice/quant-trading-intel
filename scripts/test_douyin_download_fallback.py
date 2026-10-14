"""Exercise API failure -> browser -> ASR -> single final retry accounting."""
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from prepare_douyin_ingestion import prepare, PROFILES


class FallbackPipelineTests(unittest.TestCase):
    def exercise(self, recovered):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); sid='douyin_jiujiujiucai'; cfg=PROFILES[sid]
            (root/'data').mkdir(); (root/'scripts').mkdir(); (root/'scripts/enrich_douyin_audio.py').touch()
            with sqlite3.connect(root/'data/quant_intel.sqlite') as db:
                db.execute('CREATE TABLE information_items(source_id,external_id,raw_json,created_at)')
            works=[{'aweme_id':str(n),'title':'public','ownership_verified':True,'profile_url':cfg['profile_url'],
                    'created_at':'2026-10-15T00:00:00Z'} for n in range(100,105)]
            snapshot=root/cfg['snapshot']; snapshot.parent.mkdir(parents=True)
            snapshot.write_text(json.dumps({'works':works}))
            events=[]
            def run(command,**kwargs):
                events.append('builder' if '-m' in command else Path(command[1]).stem)
                def arg(name):return Path(command[command.index(name)+1])
                if 'enrich_douyin_audio.py' in command[1]:
                    data=json.loads(arg('--snapshot').read_text())
                    selected=command[command.index('--ids')+1:]
                    self.assertEqual(len(selected),3)
                    for work in data['works']:
                        if work['aweme_id'] in selected:work['transcription_error']='metadata_missing http=403'
                    arg('--snapshot').write_text(json.dumps(data))
                elif 'transcribe_douyin_batch.py' in command[1]:
                    self.assertTrue(recovered)
                    self.assertEqual(events[-2],'playback')
                    arg('--output-dir').mkdir(parents=True,exist_ok=True)
                    for aid in command[command.index('--ids')+1:]:(arg('--output-dir')/(aid+'.json')).write_text('{}')
                else:
                    rows=json.loads(arg('--snapshot').read_text())['works']
                    docs=[{'external':{'id':w['aweme_id']},'raw_payload':{'transcription':{
                        'status':'complete' if recovered and w['aweme_id'] in {'100','101','102'} else 'pending_retry',
                        'error':w.get('transcription_error')}}} for w in rows]
                    arg('--output').write_text(''.join(json.dumps(d)+'\n' for d in docs))
                return subprocess.CompletedProcess(command,0,stdout='{}',stderr='')
            def browser(root,run_id,ids,**kwargs):
                events.append('playback');self.assertFalse(kwargs['record']);self.assertEqual(ids,['100','101','102'])
                if recovered:
                    (root/'data/douyin_metadata').mkdir(exist_ok=True)
                    for aid in ids:(root/'data/douyin_metadata'/(aid+'_data.json')).write_text('{}')
                return [{'id':aid,'status':'awaiting_transcription' if recovered else 'pending_retry',
                         'error':'verification_required'} for aid in ids]
            with patch('prepare_douyin_ingestion._candidate_works',return_value=works),patch('subprocess.run',side_effect=run),patch('capture_douyin_playback.capture',side_effect=browser),patch.dict(os.environ,{'QUANT_RUN_ID':'test_fallback'}):
                report=prepare(root,sid)
            self.assertEqual(report['enrichment_items'],3)
            with sqlite3.connect(root/'data/quant_intel.sqlite') as db:
                attempts=db.execute('SELECT attempts,status,error FROM douyin_retry_attempts').fetchall()
            self.assertEqual(len(attempts),3)
            self.assertTrue(all(row[0]==1 for row in attempts))
            if recovered:self.assertTrue(all(row[1]=='awaiting_review' for row in attempts))
            else:
                self.assertNotIn('transcribe_douyin_batch',events)
                self.assertTrue(all(row[2]=='verification_required' for row in attempts))

    def test_403_browser_success_continues_asr_and_counts_once(self):self.exercise(True)
    def test_browser_verification_stops_asr_and_counts_once(self):self.exercise(False)

if __name__=='__main__':unittest.main()
