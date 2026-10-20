import tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image
from bake_resample import reduce_image

class ResampleTests(unittest.TestCase):
 def setUp(self):self.directory=tempfile.TemporaryDirectory();self.root=Path(self.directory.name)
 def tearDown(self):self.directory.cleanup()
 def reduce(self,array,channel,size):
  source=self.root/'source.png';target=self.root/'target.png';Image.fromarray(array.astype(np.uint8)).save(source);reduce_image(source,target,channel,size);return np.asarray(Image.open(target))
 def test_color_reduction_preserves_linear_light_energy(self):
  a=np.zeros((32,32,3),dtype=np.uint8);a[:,::2]=255;out=self.reduce(a,'BaseColor',8);self.assertTrue(np.all(np.abs(out[2:-2,2:-2].astype(int)-188)<=1))
 def test_data_values_are_linear_and_constant_values_stay_constant(self):
  a=np.zeros((32,32,3),dtype=np.uint8);a[:,::2]=255;out=self.reduce(a,'Roughness',8);self.assertTrue(np.all(np.abs(out[2:-2,2:-2].astype(int)-128)<=1))
  for channel in ['BaseColor','Roughness','Metallic']:
   out=self.reduce(np.full((32,32,3),73,dtype=np.uint8),channel,8);self.assertTrue(np.all(out==73))
 def test_normal_average_is_renormalized_and_neutral_is_preserved(self):
  a=np.empty((32,32,3),dtype=np.uint8);a[:,::2]=(204,128,230);a[:,1::2]=(51,128,230);out=self.reduce(a,'Normal',8);v=out[2:-2,2:-2].astype(np.float32)/127.5-1;self.assertLess(float(np.abs(np.linalg.norm(v,axis=2)-1).max()),.012);self.assertTrue(np.all(out[2:-2,2:-2,2]>=254))
  out=self.reduce(np.tile([128,128,255],(32,32,1)),'Normal',8);self.assertTrue(np.all(out==[128,128,255]))
if __name__=='__main__':unittest.main()
