import unittest,tempfile
from pathlib import Path
from export_selection import validate_selection,select_images
from texture_bundle import pack
from PIL import Image
import zipfile
from types import SimpleNamespace
from unittest.mock import patch
from export_selection import catalogue
from project import write_json

class ExportSelectionTests(unittest.TestCase):
 def test_current_contract_includes_new_atlas_even_if_preview_manifest_is_stale(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'old-preview').mkdir()
   write_json(root/'old-preview/manifest.json',{'regions':{'old':{'original_texture':'old_c.png'}}})
   contract={'model':'native/model.blend','repair_manifest':'native/repair.json','regions':{'new':{'texture_name':'new_c.png'}}}
   project=SimpleNamespace(root=root,contract=contract,native_contract=contract,config={'type':'surface-planes','models':[str(root/'old-preview/model.blend')]})
   with patch('export_selection.plan',return_value=(root/'native/model.blend',{},None,{'new_c.png':[]})) as planner,patch('export_selection.export_name_map',return_value={('new_c.png','color'):'new_Basecolor.png'}):
    files=catalogue(project,'color')
   self.assertEqual(set(planner.call_args.args[1]),{'new'})
   self.assertEqual([r['filename'] for r in files],['new_Basecolor.png'])

 def test_selection_uses_original_filenames_and_defaults_to_all(self):
  available=[{'filename':'tank_Basecolor.png'},{'filename':'tank_Normal.png'}]
  self.assertIsNone(validate_selection(None,available))
  self.assertEqual(validate_selection(['tank_Normal.png','tank_Normal.png'],available),['tank_Normal.png'])
  for bad in [[],['domain-123-normal.png'],['../tank_Normal.png'],'tank_Normal.png']:
   with self.assertRaises(ValueError):validate_selection(bad,available)

 def test_flat_package_and_export_directory_contain_only_selected_changed_file(self):
  with tempfile.TemporaryDirectory() as temp:
   out=Path(temp);(out/'export').mkdir();files=[]
   for name in ['tank_Basecolor.png','tank_Normal.png','tank_Roughness.png']:
    path=out/'export'/name;Image.new('RGB',(8,8)).save(path);files.append(path)
   selected=select_images(files,['tank_Normal.png'],out);bundle=pack(out,'selected.zip',selected)
   self.assertEqual([p.name for p in (out/'export').iterdir()],['tank_Normal.png'])
   with zipfile.ZipFile(bundle) as archive:self.assertEqual(archive.namelist(),['tank_Normal.png'])

 def test_no_changed_selected_texture_is_explicit_error(self):
  with tempfile.TemporaryDirectory() as temp:
   with self.assertRaisesRegex(ValueError,'没有已修改'):select_images([],['stock_Normal.png'],Path(temp))

 def test_saved_long_selection_retains_original_atlas_when_names_collide(self):
  available=[{'filename':'tank_Basecolor.png','original_filename':'tank_c_us_camo_green_Basecolor.png'},
             {'filename':'tank_2_Basecolor.png','original_filename':'tank_c_Basecolor.png'}]
  self.assertEqual(validate_selection(['tank_c_Basecolor.png'],available),['tank_2_Basecolor.png'])
  with tempfile.TemporaryDirectory() as temp:
   out=Path(temp);(out/'export').mkdir();files=[]
   for row in available:
    path=out/'export'/row['filename'];Image.new('RGB',(8,8)).save(path);files.append(path)
   audit={'file_aliases':{r['original_filename']:r['filename'] for r in available}}
   selected=select_images(files,['tank_c_Basecolor.png'],out,audit)
   self.assertEqual([p.name for p in selected],['tank_2_Basecolor.png'])

if __name__=='__main__':unittest.main()
