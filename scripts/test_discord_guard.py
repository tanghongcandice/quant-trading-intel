import copy,json,sqlite3,tempfile,unittest
from pathlib import Path
from app.services.discord_guard import duplicate,target,enforce,TIANYI
ROOT=Path(__file__).resolve().parents[1]
def item(source,text='Bet call GLD',date='2026-08-28T14:32:03Z'):
 return {'source':{'id':source},'author':{'external_id':'1089568152251273228'},'content':{'text':text},'timestamps':{'created_at':date},'raw_payload':{},'relations':{}}
class Tests(unittest.TestCase):
 def test_rules(self):
  a=item(TIANYI);b=item('discord_club500_edgerunner_messages','Bet call GLD\n下注 GLD 吧')
  self.assertTrue(duplicate(a,b))
  b['timestamps']['created_at']='2026-06-24T13:31:14Z';self.assertFalse(duplicate(a,b))
  b=item('discord_club500_edgerunner_messages','Bet call GLD tomorrow');self.assertFalse(duplicate(a,b))
  b=item(TIANYI);self.assertFalse(duplicate(a,b))
  b=item('discord_club500_edgerunner_messages');b['relations']={'is_reply':True};self.assertFalse(duplicate(a,b))
  b=item('discord_club500_edgerunner_messages');a['raw_payload']={'media':{'static_images':[{'sha256':'a'}]}};b['raw_payload']={'media':{'static_images':[{'sha256':'b'}]}};self.assertFalse(duplicate(a,b))
  b['author']={'display_name':'Dalin'};self.assertFalse(target(b))
 def test_live_copy(self):
  with tempfile.TemporaryDirectory() as d:
   db=sqlite3.connect(Path(d)/'test.sqlite');db.row_factory=sqlite3.Row
   with sqlite3.connect(ROOT/'data/quant_intel.sqlite') as live:live.backup(db)
   with db: result=enforce(db,'guard_test')
   print('COPY_RESULT',result)
   self.assertEqual(db.execute("select count(*) from information_items where external_id='1542904604189261894'").fetchone()[0],0)
   self.assertEqual(db.execute("select count(*) from information_items where external_id='1542904627463463022'").fetchone()[0],1)
   for raw, in db.execute("select raw_json from information_items where external_id in ('1544368696322031657','1544368705608224798')"):
    self.assertEqual(json.loads(raw)['raw_payload']['analysis_role'],'reply_context_only')
   self.assertEqual(db.execute('pragma integrity_check').fetchone()[0],'ok')
   with db:self.assertEqual(enforce(db,'again'),{'duplicates_removed':0,'non_target_hidden':0})
if __name__=='__main__':unittest.main()
