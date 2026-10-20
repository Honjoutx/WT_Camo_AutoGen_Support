"""Resource scheduling and byte-exact lossless export regression checks."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import export_runtime as runtime


class ExportRuntimeTests(unittest.TestCase):
    def tearDown(self):runtime.configure('max')

    def test_parallel_jobs_respect_memory_and_return_input_order(self):
        capacity={'logical_cpus':8,'ram_budget_bytes':200}
        lock=threading.Lock();active=0;peak=0
        def work(value):
            nonlocal active,peak
            with lock:active+=1;peak=max(peak,active)
            time.sleep(.01*(4-value))
            with lock:active-=1
            return value*2
        runtime.configure('max')
        with patch.object(runtime,'resources',return_value=capacity):
            result=runtime.ordered_map(work,[0,1,2,3],estimate=lambda _:100)
        self.assertEqual(result,[0,2,4,6]);self.assertEqual(peak,2)

    def test_large_task_can_run_alone_and_errors_are_not_swallowed(self):
        runtime.configure('max')
        with patch.object(runtime,'resources',return_value={'logical_cpus':8,'ram_budget_bytes':1}):
            self.assertEqual(runtime.ordered_map(lambda x:x,[1,2],estimate=lambda _:100),[1,2])
            with self.assertRaisesRegex(RuntimeError,'failed'):
                runtime.ordered_map(lambda _:(_ for _ in ()).throw(RuntimeError('failed')),[1])

    def test_fast_png_retains_all_pixels_and_16bit_depth(self):
        rng=np.random.default_rng(14)
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            for channels,dtype in [(1,np.uint8),(3,np.uint8),(4,np.uint8),(1,np.uint16)]:
                shape=(67,71) if channels==1 else (67,71,channels)
                pixels=rng.integers(0,256 if dtype==np.uint8 else 65536,shape,dtype=dtype)
                for mode in ('serial','max'):
                    runtime.configure(mode);path=folder/(mode+'.png');runtime.save_png(Image.fromarray(pixels),path)
                    with Image.open(path) as image:
                        self.assertTrue(np.array_equal(np.asarray(image),pixels))
            self.assertFalse(list(folder.glob('*.tmp')))

    def test_mapping_archive_is_numpy_compatible(self):
        arrays={'u':np.arange(30,dtype=np.float32).reshape(5,6),'kind':np.full((5,6),255,np.uint8),'face':np.arange(30,dtype=np.int32).reshape(5,6)}
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'mapping.npz';runtime.configure('max');runtime.save_mapping(path,**arrays)
            with np.load(path,allow_pickle=False) as saved:
                for key,value in arrays.items():self.assertTrue(np.array_equal(value,saved[key]))

    def test_cache_reuses_and_evicts_decoded_planes(self):
        runtime.configure('max');calls=[]
        def loader():calls.append(1);return np.zeros(4,np.uint8)
        with patch.object(runtime,'resources',return_value={'ram_budget_bytes':8}):
            cache=runtime.ArrayCache();first=cache.get('a',loader,4)
            self.assertIs(cache.get('a',loader,4),first)
            cache.get('b',loader,4);cache.get('c',loader,4)
        self.assertEqual(len(calls),3);self.assertNotIn('a',cache.items);self.assertEqual(cache.bytes,8)

    def test_plane_material_render_matches_disk_renderer_and_scalar_formula(self):
        from plane_render import render
        from raster import svg_png
        with tempfile.TemporaryDirectory() as temp:
            results=[]
            for use_disk in (False,True):
                folder=Path(temp)/str(use_disk)
                for name in ('planes','previews'):(folder/name).mkdir(parents=True,exist_ok=True)
                task=dict(key='plane',out=str(folder),pixels=[8,8],has_art=True,finish={},metadata={},
                    svg='<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="#efb410"/></svg>',
                    materials={'metallic':'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="#102000"/></svg>','roughness':None})
                callback=(lambda svg,width,path:path.write_bytes(svg_png(svg,width))) if use_disk else None
                row=render(task,callback)
                results.append({ch:np.asarray(Image.open(folder/row[ch])).copy() for ch in ('color','metallic','roughness')})
                self.assertEqual(int(results[-1]['metallic'][0,0]),177)
            for channel in results[0]:self.assertTrue(np.array_equal(results[0][channel],results[1][channel]))


if __name__=='__main__':unittest.main()
