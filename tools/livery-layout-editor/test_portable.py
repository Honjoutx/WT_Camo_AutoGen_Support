"""Deployment regressions on synthetic files, isolated from user workspace."""
from pathlib import Path
import json,os,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from model_intake import execute,parse_obj
import runtime

class PortableTests(unittest.TestCase):
 def test_npm_shim_resolves_native_binary_without_shell(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);shim=base/'codex.cmd';shim.write_text('@echo off')
   native=base/'node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/codex/codex.exe'
   native.parent.mkdir(parents=True);native.touch()
   with patch.dict(os.environ,{'WT_CAMO_CODEX':str(shim)}):
    self.assertEqual(Path(runtime.codex_executable()),native)

 def test_clean_external_workspace_bootstraps_and_keeps_skill_local(self):
  with tempfile.TemporaryDirectory() as tmp:
   env={**os.environ,'WT_CAMO_WORKSPACE':tmp,'PYTHONUTF8':'1'}
   result=subprocess.run([sys.executable,str(runtime.HERE/'bootstrap.py')],env=env,capture_output=True)
   self.assertEqual(result.returncode,0,result.stderr.decode('utf8',errors='replace'))
   root=Path(tmp);registry=json.loads((root/'projects/registry.json').read_text(encoding='utf8'))
   self.assertEqual(list(registry['projects']),['starter'])
   self.assertTrue((root/'.agents/skills/wt-camo-workflow/SKILL.md').is_file())
   source=root/'projects/starter/sources/body-left-editable.svg';old=source.read_bytes()
   subprocess.run([sys.executable,str(runtime.HERE/'bootstrap.py')],env=env,check=True,capture_output=True)
   self.assertEqual(source.read_bytes(),old)
   subprocess.run([sys.executable,str(runtime.HERE/'project_cli.py'),'new','--id','new-study','--name','New study'],env=env,check=True,capture_output=True)
   new_registry=json.loads((root/'projects/registry.json').read_text(encoding='utf8'))
   self.assertEqual(new_registry['active_project'],'new-study')
   self.assertEqual(new_registry['projects']['new-study']['shared_library'],'common')
   self.assertFalse((root/'projects/new-study/state/codex').exists())

 def test_intake_keeps_geometry_and_repairs_material_phase(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source.obj'
   source.write_text('mtllib source.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 1.2\nvt 1 1.2\nvt 0 1.9\nvn 0 0 1\no hull\nusemtl paint\nf 1/1/1 2/2/1 3/3/1\no track_left\nf 1/1/1 2/2/1 3/3/1\n',encoding='utf8')
   (root/'source.mtl').write_text('newmtl paint\nKd 1 1 1\n',encoding='utf8')
   out=root/'fixed';execute(source,out,{'uv_mode':'auto','up_axis':'y'})
   files=list(out.glob('*.obj'));self.assertTrue(files)
   original=parse_obj(source)
   found=False
   for target in files:
    parsed=parse_obj(target)
    self.assertEqual(parsed[0],original[0]);self.assertEqual(parsed[2],original[2])
    if any(o['name']=='body' for o in parsed[3]):
     found=True
     for obj in parsed[3]:
      if obj['name']=='body':
       for face in obj['faces']:
        self.assertEqual([round(parsed[1][c[1]-1][1],6) for c in face['corners']],[.2,.2,.9])
   self.assertTrue(found)

if __name__=='__main__':unittest.main()
