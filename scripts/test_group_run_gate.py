import hashlib, json, sys, tempfile, unittest
from pathlib import Path
from datetime import datetime, timezone
from prepare_douyin_group_run import prepare
from group_test_support import setup, ready
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'packages/ingestion_scheduler/src'))
from ingestion_scheduler.adapters.douyin import DouyinAdapter
from ingestion_scheduler.adapters.base import AdapterContext

class GateTests(unittest.TestCase):
    def test_fresh_empty_and_replay_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); setup(root); payload=ready(root)
            path=root/'runs/test/group_checkpoint.json'
            payload['collection_evidence']['pending_voice_count']=1
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):prepare(root,'test')
            payload['collection_evidence']['pending_voice_count']=0
            path.write_text(json.dumps(payload)); prepare(root,'test')
            receipt=json.loads((root/'runs/test/group_receipt.json').read_text())
            (root/'runs/test/chrome_preflight_diagnostics.jsonl').write_text('')
            validation={'ready':True,'run_id':'test','sha256':receipt['sha256'],'capture_sha256':receipt['capture_sha256'],'diagnostics_sha256':hashlib.sha256(b'').hexdigest()}
            (root/'runs/test/chrome_preflight_validation.json').write_text(json.dumps(validation))
            source={'id':'group','browser_snapshot':'data/douyin_built/yuboluo_group_1.jsonl','require_run_capture':True}
            context=AdapterContext(root,'test',root/'runs/test',root/'runs/test/raw',payload['captured_at'],False,30)
            self.assertEqual(len(DouyinAdapter().collect(source,context).items),1)
            (root/'runs/test/chrome_preflight_diagnostics.jsonl').write_text('later failure')
            with self.assertRaisesRegex(RuntimeError,'changed after validation'):DouyinAdapter().collect(source,context)
            (root/'runs/test/chrome_preflight_diagnostics.jsonl').write_text('')
            context.run_id='other'
            with self.assertRaises(RuntimeError):DouyinAdapter().collect(source,context)
            context.run_id='test'
            (root/source['browser_snapshot']).write_text('[]')
            self.assertEqual(len(DouyinAdapter().collect(source,context).items),1)
            (root/'runs/test/group_items.jsonl').write_text('[]')
            with self.assertRaises(RuntimeError):DouyinAdapter().collect(source,context)

if __name__=='__main__':unittest.main()
