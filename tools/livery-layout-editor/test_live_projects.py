import copy,json,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from live_projects import LiveProjects,state_revision,save_conflict
from workflow import catalogue

class LiveTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.web=self.root/'web';self.web.mkdir();(self.web/'app.js').write_text('app');(self.web/'style.css').write_text('style')
  self.folder=self.root/'project';surface=self.folder/'surfaces/v1';(surface/'sources').mkdir(parents=True);(surface/'sources/main.svg').write_text('<svg/>');(surface/'contract.json').write_text('{}');state=self.folder/'state/surface-v1';state.mkdir(parents=True);(state/'current.json').write_text('{"regions":{}}')
  config={'id':'fixture','name':'Current project','directory':'project','type':'surface-planes','surface_directory':'surfaces/v1'}
  self.manager=SimpleNamespace(lock=threading.RLock(),registry={'active_project':'fixture','projects':{'fixture':config},'libraries':{}},cache={})
  self.live=LiveProjects(self.manager,self.root,self.web)
 def test_revision_is_stable_and_ignores_job_output(self):
  a=self.live.revision('fixture');p=self.folder/'outputs/job/textures/a.png';p.parent.mkdir(parents=True);p.write_bytes(b'cache')
  self.assertEqual(a,self.live.revision('fixture'))
 def test_sources_and_state_have_distinct_revisions(self):
  a=self.live.revision('fixture');(self.folder/'state/surface-v1/current.json').write_text('{"regions":{"main":{}}}');b=self.live.revision('fixture')
  self.assertEqual(a['design_revision'],b['design_revision']);self.assertNotEqual(a['state_revision'],b['state_revision'])
  (self.folder/'surfaces/v1/sources/main.svg').write_text('<svg>new</svg>');c=self.live.revision('fixture');self.assertNotEqual(b['design_revision'],c['design_revision'])
 def test_identical_asset_index_rewrite_does_not_trigger_reload(self):
  p=self.folder/'cache/asset-library/index.json';p.parent.mkdir(parents=True);p.write_text('{"a":1,"b":2}');a=self.live.revision('fixture');p.write_text('{ "b": 2, "a": 1 }');self.assertEqual(a,self.live.revision('fixture'))
 def test_css_and_script_revisions_are_separate(self):
  a=self.live.revision('fixture');(self.web/'style.css').write_text('new css');b=self.live.revision('fixture');self.assertNotEqual(a['style_revision'],b['style_revision']);self.assertEqual(a['ui_revision'],b['ui_revision']);(self.web/'app.js').write_text('new app');self.assertNotEqual(b['ui_revision'],self.live.revision('fixture')['ui_revision'])
 def test_disk_registry_is_reloaded_without_switching_ui_project(self):
  registry=copy.deepcopy(self.manager.registry);registry['projects']['fixture']['name']='Updated';p=self.root/'projects/registry.json';p.parent.mkdir();p.write_text(json.dumps(registry));self.live.revision('fixture');self.assertEqual(self.manager.registry['projects']['fixture']['name'],'Updated')
 def test_optimistic_save_detects_background_write(self):
  before=self.live.revision('fixture');data={'base_state_revision':before['state_revision'],'base_design_revision':before['design_revision']};self.assertFalse(save_conflict(data,before));(self.folder/'state/surface-v1/current.json').write_text('{"changed":true}');self.assertTrue(save_conflict(data,self.live.revision('fixture')));self.assertFalse(save_conflict({},before))
 def test_public_guide_has_generic_stages_and_no_project_case_dump(self):
  c=catalogue();self.assertEqual(len(c['stages']),10);text=json.dumps(c,ensure_ascii=False)
  self.assertNotIn('task-history-index',text)

if __name__=='__main__':unittest.main()
