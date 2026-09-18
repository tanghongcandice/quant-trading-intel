import copy
import json
import tempfile
import unittest
from pathlib import Path
from group_test_support import setup, window
from group_capture_checkpoint import checkpoint
from prepare_douyin_group_run import prepare
from build_douyin_group import build


class PartialTests(unittest.TestCase):
    def test_card_does_not_block_voice_and_cursor_is_held(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup(root)
            w = window()
            for row in w['messages']:
                row['index'] += 1
            w['messages'].insert(0, {'index': 0, 'author': '宇菠萝',
                'role': '管理员', 'time': '09/15 11:36', 'text': '分享视频',
                'message_kind': 'video_share'})
            checkpoint(root, 'partial', w)
            checkpoint(root, 'partial', w)
            receipt = prepare(root, 'partial')
            self.assertEqual(receipt['status'], 'partial_ready')
            items = [json.loads(s) for s in (root/'runs/partial/group_items.jsonl').read_text().splitlines()]
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]['raw_payload']['transcription']['audio_count'], 2)
            self.assertFalse(items[0]['raw_payload']['group_capture_progress']['complete'])
            from ingestion_scheduler.runner import _cursor_eligible
            self.assertFalse(_cursor_eligible(items[0], {'type': 'douyin'}))
            from app.services.ingestion_service import import_jsonl
            import sqlite3
            db = root/'data/quant_intel.sqlite'
            with sqlite3.connect(db) as c:
                before = c.execute('select * from source_cursors').fetchall()
            import_jsonl(db, root/'runs/partial/group_items.jsonl', 'partial')
            with sqlite3.connect(db) as c:
                self.assertEqual(c.execute('select * from source_cursors').fetchall(), before)

    def test_incomplete_voice_batch_is_not_split(self):
        p = window()
        p['messages'][0]['voice'] = ''
        self.assertEqual(build(p, allow_partial=True), [])
        with self.assertRaises(ValueError):
            build(p)

    def test_tampering_still_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup(root)
            w = window()
            checkpoint(root, 'test', w)
            checkpoint(root, 'test', w)
            path = root/'runs/test/group_checkpoint.json'
            p = json.loads(path.read_text())
            p['messages'][0]['voice'] = 'invented'
            path.write_text(json.dumps(p))
            with self.assertRaises(ValueError):
                prepare(root, 'test')


if __name__ == '__main__':
    unittest.main()
