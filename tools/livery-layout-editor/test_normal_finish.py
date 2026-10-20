import unittest
import numpy as np
from normal_finish import decode,unit,finish_composed,soften
from surface_relief import combine_normals

class NormalFinishTests(unittest.TestCase):
 def test_rnm_inverse_keeps_embossing_and_original_outside_coverage(self):
  size=96;y,x=np.mgrid[:size,:size];base=unit(np.dstack([.12*np.sin(x*.8),.08*np.cos(y*.7),np.ones_like(x)]));rgb=np.uint8(np.rint((base+1)*127.5));detail=unit(np.dstack([.10*np.exp(-((x-48)/6)**2),np.zeros_like(x),np.ones_like(x)]));mask=np.zeros((size,size),bool);mask[8:-8,8:-8]=True;old=combine_normals(rgb,detail,mask,.45)
  same=finish_composed(old,rgb,mask,.45,{'enabled':False})
  self.assertLessEqual(np.max(np.abs(same.astype(int)-old)),1)
  cfg={'enabled':True,'base_radius_px_at_2k':35,'base_strength':.85,'detail_radius_px_at_2k':0,'detail_strength':1}
  new=finish_composed(old,rgb,mask,.45,cfg)
  self.assertTrue(np.array_equal(new[~mask],old[~mask]))
  old_noise=np.std(np.diff(decode(old)[20:75,15:32,0],axis=1));new_noise=np.std(np.diff(decode(new)[20:75,15:32,0],axis=1));self.assertLess(new_noise,old_noise*.7)
  self.assertGreater(decode(new)[48,48,0],.07)

 def test_large_seam_and_uv_boundary_survive_grain_smoothing(self):
  size=128;y,x=np.mgrid[:size,:size];slope=np.where(x<64,.0,.7)+.035*np.sin(x*2.7)*np.cos(y*2.4);n=unit(np.dstack([slope,np.zeros_like(slope),np.ones_like(slope)]));mask=np.ones((size,size),bool);mask[:,60:62]=False
  new=soften(n,mask,25,.85,.18)
  self.assertTrue(np.array_equal(new[~mask],n[~mask]))
  self.assertGreater(new[64,65,0],.5)
  self.assertLess(np.std(new[25:105,25:50,0]),np.std(n[25:105,25:50,0])*.6)
  self.assertTrue(np.isfinite(new).all());self.assertLess(np.max(abs(np.linalg.norm(new,axis=2)-1)),1e-6)

 def test_small_component_island_uses_atlas_radius_and_preserves_other_pixels(self):
  size=256;y,x=np.mgrid[:size,:size];base=unit(np.dstack([.12*np.sin(x*1.7),.05*np.cos(y*1.3),np.ones_like(x)]));rgb=np.uint8(np.rint((base+1)*127.5));detail=unit(np.dstack([.04*np.sin(x*.1),np.zeros_like(x),np.ones_like(x)]));mask=np.zeros((size,size),bool);mask[100:140,100:150]=True;old=combine_normals(rgb,detail,mask,.45);cfg={'enabled':True,'base_radius_px_at_2k':12,'detail_radius_px_at_2k':2,'base_strength':.85,'detail_strength':.92}
  direct=combine_normals(rgb,detail,mask,.45,cfg);cropped=finish_composed(old,rgb,mask,.45,cfg)
  self.assertTrue(np.array_equal(cropped[~mask],old[~mask]));self.assertLessEqual(np.max(abs(cropped.astype(int)-direct.astype(int))),2)

if __name__=='__main__':unittest.main()
