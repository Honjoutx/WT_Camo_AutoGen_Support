"""Parallel UV domains must preserve overlaps, padding and source-only pixels."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from PIL import Image
from project import sha,write_json
from surface_bake import bake
import export_runtime as runtime


class SurfaceParallelTests(unittest.TestCase):
    def tearDown(self):runtime.configure('max')

    def test_parallel_and_serial_bakes_match_with_face_overlap_and_masks(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);model=root/'model';model.mkdir();(model/'textures').mkdir()
            source=model/'model.blend';source.write_bytes(b'geometry-fixture')
            uv=np.array([[.15,.15],[.85,.15],[.15,.85]],np.float32)
            np.savez(model/'source-bindings.npz',tri=np.array([[0,1,2],[0,1,2]]),tex=np.array([[0,1,2],[0,1,2]]),uv_fixed=uv,
                     material_index=np.array([0,0]),owner=np.array([0,0]),paint=np.ones(2,bool))
            Image.new('RGB',(32,32),(10,20,30)).save(model/'textures/base.png')
            write_json(model/'repair.json',{'materials':{'source':{'map_Kd':'textures/base.png'}}})
            surface=root/'surface';surface.mkdir()
            write_json(surface/'capture.json',{'model_sha256':sha(source)})
            np.savez(surface/'capture.npz',a_selected_face_ids=np.array([0]),a_art_uv=uv[None],
                     b_selected_face_ids=np.array([1]),b_art_uv=uv[None])
            mask=Image.new('L',(32,32));mask.paste(255,(2,2,30,30));mask.save(model/'mask.png')
            contract={'capture_session':'capture.json','capture_bindings':'capture.npz'}
            native={'model':str(source),'repair_manifest':str(model/'repair.json'),'regions':{
                k:{'name':k,'color_map':'textures/base.png','texture_name':'base.png','mask':str(model/'mask.png')}
                for k in ('one','two','three')}}
            results=[]
            for mode in ('serial','max'):
                out=root/mode
                for folder in ('planes','textures','materials','evidence'):(out/folder).mkdir(parents=True,exist_ok=True)
                planes={}
                for key,color in [('a',(255,0,0,255)),('b',(0,255,0,255))]:
                    row={'pixels':[32,32]}
                    for ch,image in [('color',Image.new('RGBA',(32,32),color)),('metallic',Image.new('L',(32,32),200)),('roughness',Image.new('L',(32,32),50))]:
                        row[ch]=f'planes/{key}-{ch}.png';image.save(out/row[ch])
                    planes[key]=row
                p=SimpleNamespace(root=out,surface_root=surface,contract=contract,native_contract=native,regions={'a':{},'b':{}})
                runtime.configure(mode,out)
                with patch.object(runtime.os,'cpu_count',return_value=8):rows=bake(p,planes,out,32)
                pixels={k:np.asarray(Image.open(out/row['color'])).copy() for k,row in rows.items()}
                self.assertTrue(np.array_equal(pixels['one'][20,8],[0,255,0])) # last face wins
                self.assertTrue(np.array_equal(pixels['one'][0,0],[10,20,30]))
                results.append(pixels)
            for key in results[0]:self.assertTrue(np.array_equal(results[0][key],results[1][key]))
            report=json.loads((root/'max/evidence/export-performance.json').read_text())
            self.assertEqual(report['stages']['native_domains']['peak_workers'],3)


if __name__=='__main__':unittest.main()
