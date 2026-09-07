import json, sys, tempfile, unittest
from pathlib import Path
from datetime import datetime, timezone
from prepare_douyin_group_run import prepare
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'packages/ingestion_scheduler/src'))
from ingestion_scheduler.adapters.douyin import DouyinAdapter
from ingestion_scheduler.adapters.base import AdapterContext

class GateTests(unittest.TestCase):
    def test_fresh_empty_and_replay_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/'data/browser_sessions/douyin_group_yuboluo_1.json'
            path.parent.mkdir(parents=True)
            payload={'group_name':'宇菠萝的认知圈1群','captured_at':datetime.now(timezone.utc).isoformat(),'messages':[]}
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):prepare(root,'test')
            payload['collection_evidence']={'run_id':'test','latest_checked':True,'overlap_covered':True,'pending_voice_count':1}
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):prepare(root,'test')
            payload['collection_evidence']['pending_voice_count']=0
            path.write_text(json.dumps(payload)); prepare(root,'test')
            source={'id':'group','browser_snapshot':'data/douyin_built/yuboluo_group_1.jsonl','require_run_capture':True}
            context=AdapterContext(root,'test',root/'runs/test',root/'runs/test/raw',payload['captured_at'],False,30)
            self.assertEqual(DouyinAdapter().collect(source,context).items,[])
            context.run_id='other'
            with self.assertRaises(RuntimeError):DouyinAdapter().collect(source,context)
            context.run_id='test'
            (root/source['browser_snapshot']).write_text('[]')
            with self.assertRaises(RuntimeError):DouyinAdapter().collect(source,context)

if __name__=='__main__':unittest.main()
