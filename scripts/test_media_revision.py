import copy,json,sqlite3,sys,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'apps/api'))
from app.services.media_revision import update_static_media
class MediaRevisionTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
  self.c.execute('create table information_items(id text, raw_json text)')
  self.old={'id':'item','source':{'id':'discord'},'external':{'id':'1'},'content':{'text':'body'},'timestamps':{'created_at':'original'},'raw_payload':{'discord':{'attachments':[{'url':'https://example.com/a.png'}]},'translation':'中文','media':{'static_images':[]}}}
  self.c.execute('insert into information_items values (?,?)',('item',json.dumps(self.old)))
 def candidate(self):
  import hashlib
  d=copy.deepcopy(self.old);d['raw_payload']['static_media_recovery']={'evidence':'test'}
  d['raw_payload']['media']['static_images']=[{'local_path':str(ROOT/'data/media/test.png'),'sha256':hashlib.sha256(b'image').hexdigest(),'bytes':5,'api_url':'/media/test.png','source_url':'https://example.com/a.png'}]
  return d
 def test_update_is_idempotent_and_preserves_body_translation(self):
  with patch.object(Path,'read_bytes',return_value=b'image'):
   self.assertTrue(update_static_media(self.c,self.candidate(),'run'))
   self.assertFalse(update_static_media(self.c,self.candidate(),'run'))
  after=json.loads(self.c.execute('select raw_json from information_items').fetchone()[0])
  self.assertEqual(after['content'],self.old['content']);self.assertEqual(after['raw_payload']['translation'],'中文')
  self.assertEqual(self.c.execute('select count(*) from media_revision_audit').fetchone()[0],1)
 def test_rejects_body_change_and_hash_mismatch(self):
  d=self.candidate();d['content']['text']='changed'
  with self.assertRaises(ValueError):update_static_media(self.c,d,'run')
  with patch.object(Path,'read_bytes',return_value=b'wrong'):
   with self.assertRaises(ValueError):update_static_media(self.c,self.candidate(),'run')
  self.assertEqual(json.loads(self.c.execute('select raw_json from information_items').fetchone()[0]),self.old)
if __name__=='__main__':unittest.main()
