"""Storage must save blocks without coupling editable files or losing history."""
import io,json,os,tempfile,unittest,zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
import storage,assets
from texture_bundle import pack

class StorageTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  for target,value in [('storage.STORE',self.root/'pool'),('assets.ROOT',self.root)]:
   p=patch(target,value);p.start();self.addCleanup(p.stop)
 def job(self,name,mode='compact'):
  p=self.root/name;p.mkdir();storage.write_json(p/'job.json',{'storage_mode':mode});return p
 def image(self,p):
  p.parent.mkdir(parents=True,exist_ok=True);Image.new('RGB',(23,17),'#886fff').save(p);return p
 def test_cache_shares_blocks_but_retry_and_export_are_private(self):
  a,b=self.job('a'),self.job('b');x=self.image(a/'planes/a.png');y=self.image(b/'planes/b.png');export=self.image(b/'export/b.png')
  storage.compact_job(a);r=storage.compact_job(b)
  self.assertTrue(os.path.samefile(x,y));self.assertFalse(os.path.samefile(x,export));self.assertEqual(r['reclaimed_duplicate_bytes'],y.stat().st_size)
  original=x.read_bytes();storage.prepare_job(b);y.write_bytes(b'changed')
  self.assertEqual(x.read_bytes(),original);self.assertFalse(os.path.samefile(x,y));self.assertEqual(export.read_bytes(),original)
 def test_store_does_not_link_editable_source(self):
  source=self.image(self.root/'source.png');blob,_,_=storage.ContentStore().put_file(source)
  self.assertFalse(os.path.samefile(source,blob));original=blob.read_bytes();source.write_bytes(b'updated');self.assertEqual(blob.read_bytes(),original)
 def test_asset_library_preserves_removed_source_across_projects(self):
  source=self.image(self.root/'art/source.png');a=assets.AssetLibrary(cache=self.root/'a-cache',imports=self.root/'imports',roots=[(source.parent,'角色原图')]);aid=a.list()[0]['id'];first=a.pin(aid)
  b=assets.AssetLibrary(cache=self.root/'b-cache',imports=self.root/'imports',roots=[(source.parent,'角色原图')]);self.assertEqual(first,b.pin(aid));source.unlink()
  reloaded=assets.AssetLibrary(cache=self.root/'a-cache',imports=self.root/'imports',roots=[]);self.assertEqual(reloaded.pin(aid),first);self.assertTrue(reloaded.get(aid)['archived'])
 def test_legacy_original_cache_migrates_after_proven_snapshot(self):
  source=self.image(self.root/'art/source.png');lib=assets.AssetLibrary(cache=self.root/'old-cache',imports=self.root/'imports',roots=[(source.parent,'角色原图')]);row=lib.list()[0];old=lib.cache/'originals'/(row['id']+row['suffix']);old.write_bytes(source.read_bytes());source.unlink()
  pinned=lib.pin(row['id']);self.assertFalse(old.exists());self.assertTrue(pinned.is_file());self.assertEqual(storage.digest(pinned),row['sha256'])
 def test_identical_checkpoints_and_autosaves_do_not_accumulate(self):
  p=SimpleNamespace(state_dir=self.root/'state');state={'title':'test','regions':{'side':{'layers':[]}}}
  first=storage.save_layout(p,state,True,'20261017-010203');mtime=(p.state_dir/'current.json').stat().st_mtime_ns
  again=storage.save_layout(p,state,True,'20261017-010204');auto=storage.save_layout(p,state,False,'20261017-010205')
  self.assertEqual(first['checkpoint'],again['checkpoint']);self.assertTrue(again['reused']);self.assertFalse(auto['changed']);self.assertEqual(len(list((p.state_dir/'checkpoints').glob('*.json'))),1);self.assertEqual(mtime,(p.state_dir/'current.json').stat().st_mtime_ns)
 def test_compact_final_zip_streams_without_persistent_archive(self):
  job=self.job('job');p=self.image(job/'export/tank_Basecolor.png');bundle=pack(job,'maps.zip',[p]);self.assertFalse(bundle.exists())
  compression,entries=storage.archive_entries(job,bundle.name)
  class Unseekable:
   def __init__(self):self.data=bytearray()
   def write(self,b):self.data.extend(b);return len(b)
   def flush(self):pass
  out=Unseekable();storage.stream_archive(out,compression,entries)
  with zipfile.ZipFile(io.BytesIO(out.data)) as z:self.assertEqual(z.namelist(),[p.name]);self.assertEqual(z.read(p.name),p.read_bytes());self.assertIsNone(z.testzip())
  self.assertFalse(bundle.exists())
 def test_portable_and_historical_exports_keep_real_zip(self):
  for name,record in [('portable',{'storage_mode':'portable'}),('historical',{})]:
   job=self.root/name;job.mkdir();storage.write_json(job/'job.json',record);p=self.image(job/'export/tank_Basecolor.png');bundle=pack(job,'maps.zip',[p])
   self.assertTrue(bundle.is_file())
   with zipfile.ZipFile(bundle) as z:self.assertEqual(z.read(p.name),p.read_bytes())
 def test_archive_rejects_missing_resources_and_escape(self):
  job=self.job('job');p=self.image(job/'textures/a.png');storage.register_archive(job,'x.zip',[(p,'a.png')]);p.unlink()
  with self.assertRaises(ValueError):storage.archive_entries(job,'x.zip')
  outside=self.image(self.root/'outside.png')
  with self.assertRaises(ValueError):storage.register_archive(job,'x.zip',[(outside,'a.png')])
  with self.assertRaises(ValueError):storage.register_archive(job,'../x.zip',[])
 def test_portable_cache_is_not_pooled(self):
  job=self.job('portable','portable');p=self.image(job/'planes/a.png');self.assertIsNone(storage.compact_job(job));self.assertEqual(p.stat().st_nlink,1)
 def test_portable_reuse_cannot_modify_source_cache(self):
  old=self.image(self.root/'old/source.png');job=self.job('portable','portable');target=job/'planes/copy.png'
  storage.reuse_file(old,target,job);self.assertFalse(os.path.samefile(old,target));before=old.read_bytes();target.write_bytes(b'edited');self.assertEqual(old.read_bytes(),before)
 def test_old_shared_export_cannot_corrupt_new_pool(self):
  old=self.image(self.root/'old/source.png');legacy_export=self.root/'old/export.png';os.link(old,legacy_export)
  job=self.job('new');target=job/'planes/copy.png';storage.reuse_file(old,target,job);before=target.read_bytes();storage.compact_job(job)
  self.assertFalse(os.path.samefile(target,legacy_export));legacy_export.write_bytes(b'manual repair');self.assertEqual(target.read_bytes(),before)

if __name__=='__main__':unittest.main()
