import copy, json, sqlite3, tempfile, unittest
from pathlib import Path
from group_test_support import setup, window, ready
from group_capture_checkpoint import checkpoint
from build_douyin_group import build
from douyin_group_processing_ledger import voice_batches, verified_prefix, record, reuse
from app.services.ingestion_service import import_jsonl
from prepare_douyin_group_run import prepare

def import_items(root, items, run):
    path=root/(run+'.jsonl'); path.write_text(''.join(json.dumps(i,ensure_ascii=False)+'\n' for i in items))
    return import_jsonl(root/'data/quant_intel.sqlite',path,run)

class ReliabilityTests(unittest.TestCase):
    def test_initial_old_view_can_resume_but_unknown_voice_context_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); setup(root)
            w=window(); older=copy.deepcopy(w)
            older['messages']=older['messages'][1:]; older['at_latest']=False
            checkpoint(root,'test',older)
            checkpoint(root,'test',w)
            self.assertTrue(checkpoint(root,'test',w)['ready'])
            self.assertEqual(prepare(root,'test')['status'],'ready')
            unknown=window(); unknown['messages'][1].pop('author'); unknown['messages'][1].pop('role')
            checkpoint(root,'unknown',unknown)
            result=checkpoint(root,'unknown',unknown)
            self.assertFalse(result['ready'])
            self.assertTrue(any('context' in e for e in result['errors']))

    def test_final_identity_and_transcript_are_authority_not_scheduler_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); db=setup(root); payload=ready(root)
            items=build(payload); ledger={'batches':{}}; record(payload,items,ledger)
            items[0]['id']='final-different-primary-id'
            import_items(root,items,'old')
            blank=copy.deepcopy(payload)
            for row in blank['messages']: row['voice']=''
            self.assertEqual(reuse(copy.deepcopy(blank),ledger,db)['reused_segments'],2)
            changed=copy.deepcopy(items[0]); changed['raw_payload']['message_parts'][0]['voice']='changed in final store'
            with sqlite3.connect(db) as conn:
                conn.execute('UPDATE information_items SET raw_json=?',(json.dumps(changed),))
            self.assertEqual(reuse(blank,ledger,db)['reused_segments'],0)

    def test_scheduler_emits_committed_expansion_even_before_cursor_cutoff(self):
        from unittest.mock import patch
        from ingestion_scheduler.adapters.base import AdapterContext, AdapterResult
        from ingestion_scheduler.runner import _run_source
        from ingestion_scheduler.state import StateStore
        from app.services.group_reconciliation import preserve_identity
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); db=setup(root); payload=ready(root)
            original=build(payload)[0]; import_items(root,[original],'old')
            larger=copy.deepcopy(payload)
            for row in larger['messages']: row['index']+=1
            larger['messages'].insert(0,{'index':0,'duration':'9"','voice':'新增末段。'})
            expanded=build(larger)[0]
            with sqlite3.connect(db) as conn:
                preserve_identity(conn,expanded)
                conn.execute("UPDATE source_cursors SET last_successful_created_at='2026-09-15T15:00:00+08:00'")
            state=StateStore(root/'state.sqlite')
            try:
                state.upsert_item(original,'old',payload['captured_at'])
                ctx=AdapterContext(root,'new',root/'runs/new',root/'runs/new/raw',payload['captured_at'],False,30)
                with patch('ingestion_scheduler.runner.adapter_for') as factory:
                    factory.return_value.collect.return_value=AdapterResult(source_id=original['source']['id'],source_type='douyin',items=[expanded])
                    result=_run_source(source={'id':original['source']['id'],'type':'douyin'},context=ctx,state=state,max_retries=0,retry_backoff_seconds=0,include_duplicates=False,dry_run=False,items_path=root/'emitted.jsonl',errors_path=root/'errors.jsonl')
                self.assertEqual(result['status'],'success',result)
                self.assertEqual(result['emitted_count'],1)
                self.assertEqual(result['duplicate_count'],0)
                self.assertEqual(result['new_count'],0)
                imported=import_jsonl(db,root/'emitted.jsonl','new')
                self.assertEqual(imported['updated_items'],1)
                self.assertEqual(imported['inserted_items'],0)
            finally: state.close()

    def test_missing_window_shift_and_open_batch_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); setup(root)
            w=window()
            first=copy.deepcopy(w); first['messages']=first['messages'][:2]
            self.assertFalse(checkpoint(root,'test',first)['ready'])
            shifted=copy.deepcopy(first); shifted['messages'][0]['duration']='12"'
            with self.assertRaisesRegex(ValueError,'shifted'): checkpoint(root,'test',shifted)
            gap=copy.deepcopy(w); gap['messages'][2]['index']=3
            self.assertFalse(checkpoint(root,'test',gap)['ready'])

    def test_pending_count_and_same_run_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); setup(root)
            w=window(); w['messages'][0]['voice']=''
            checkpoint(root,'test',w)
            self.assertEqual(checkpoint(root,'test',w)['pending_voice_count'],1)
            w['messages'][0]['voice']='第二段。'
            self.assertTrue(checkpoint(root,'test',w)['ready'])
            w['messages'][0]['voice']=''
            self.assertEqual(checkpoint(root,'test',w)['pending_voice_count'],0)
            self.assertEqual(checkpoint(root,'other',w)['pending_voice_count'],1)

    def test_expansion_updates_primary_id_and_fts_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); setup(root); payload=ready(root)
            original=build(payload)[0]; import_items(root,[original],'old')
            larger=copy.deepcopy(payload)
            for row in larger['messages']: row['index']+=1
            larger['messages'].insert(0,{'index':0,'duration':'9"','voice':'新增末段。'})
            expanded=build(larger)[0]; result=import_items(root,[expanded],'new')
            self.assertEqual(result['inserted_items'],0); self.assertEqual(result['updated_items'],1)
            with sqlite3.connect(root/'data/quant_intel.sqlite') as conn:
                rows=conn.execute('SELECT id,external_id,content_text FROM information_items').fetchall()
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0][:2],(original['id'],original['external']['id']))
                self.assertIn('新增末段',rows[0][2])
                self.assertEqual(conn.execute('SELECT count(*) FROM group_revision_audit').fetchone()[0],1)
                self.assertIn('新增末段',conn.execute('SELECT content_text FROM information_items_fts').fetchone()[0])
            self.assertEqual(import_items(root,[expanded],'again')['updated_items'],0)
            with self.assertRaisesRegex(ValueError,'shorter stored prefix'):
                import_items(root,[original],'shorter')

    def test_expansion_and_audit_roll_back_on_later_import_failure(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); db=setup(root); payload=ready(root)
            original=build(payload)[0]; import_items(root,[original],'old')
            larger=copy.deepcopy(payload)
            for row in larger['messages']: row['index']+=1
            larger['messages'].insert(0,{'index':0,'duration':'9"','voice':'新增末段。'})
            with patch('app.services.ingestion_service.enforce',side_effect=ValueError('late transaction failure')):
                with self.assertRaisesRegex(ValueError,'late transaction failure'):
                    import_items(root,build(larger),'failed')
            with sqlite3.connect(db) as conn:
                row=conn.execute('SELECT content_text FROM information_items').fetchone()
                self.assertEqual(row[0],original['content']['text'])
                self.assertEqual(conn.execute('SELECT content_text FROM information_items_fts').fetchone()[0],row[0])
                self.assertEqual(conn.execute("SELECT count(*) FROM ingestion_runs WHERE id='failed'").fetchone()[0],0)
                self.assertEqual(conn.execute("SELECT count(*) FROM sqlite_master WHERE name='group_revision_audit'").fetchone()[0],0)

    def test_prefix_reuse_requires_two_observed_matching_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); db=setup(root); payload=ready(root)
            import_items(root,build(payload),'old')
            larger=copy.deepcopy(payload)
            for row in larger['messages']: row['index']+=1
            larger['messages'].insert(0,{'index':0,'duration':'9"','voice':''})
            batch=voice_batches(larger)[0]
            self.assertIsNotNone(verified_prefix(batch,db))
            batch['voices'][0]='different'
            self.assertIsNone(verified_prefix(batch,db))
            batch['voices'][0]=''
            self.assertIsNone(verified_prefix(batch,db))
            with sqlite3.connect(db) as conn: conn.execute('DELETE FROM information_items')
            self.assertIsNone(verified_prefix(voice_batches(larger)[0],db))

    def test_ledger_never_merges_across_missing_index(self):
        w=window(); w['messages'][0]['index']=-1
        self.assertEqual(len(voice_batches(w)),1)
        self.assertEqual(len(voice_batches(w)[0]['indexes']),1)

    def test_fabricated_transcript_cannot_be_sealed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); setup(root); payload=ready(root)
            payload['messages'][0]['voice']='invented'
            (root/'runs/test/group_checkpoint.json').write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError,'provenance'): prepare(root,'test')
