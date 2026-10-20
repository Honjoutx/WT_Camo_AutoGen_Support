import unittest,sys,copy,io,math
from pathlib import Path
H=Path(__file__).resolve().parent;R=H.parents[1];
import resvg_py
from PIL import Image
from test_helpers import fixture_project
from layer_material import compose_material
class MaterialsTests(unittest.TestCase):
 def test_alpha_occlusion_inheritance_and_fixed_transformed_clip(self):
  # Blue/right pixels matter only for alpha. A .5-opacity inherited top covers
  # half the custom foil; opaque inherited front restores automatic completely.
  svg='<svg xmlns="http://www.w3.org/2000/svg" width="32" height="8" viewBox="0 0 32 8"><defs><clipPath id="p"><rect width="28" height="8"/></clipPath></defs><g clip-path="url(#p)" data-shared-fixed-clip="url(#p)"><g id="layout-a" transform="translate(4)"><rect width="24" height="8" fill="blue"/></g><g id="layout-b" opacity=".5"><rect x="10" width="8" height="8" fill="white"/></g><g id="layout-c"><rect x="18" width="6" height="8" fill="white"/></g><g id="layout-d" display="none"><rect width="32" height="8" fill="red"/></g></g></svg>'
  layers=[{'id':k,'visible':k!='d','opacity':.5 if k=='b' else 1,'material':{'metallic':.8 if k in ['a','d'] else None}} for k in 'abcd'];state={'regions':{'r':{'layers':layers}}}
  data=compose_material(svg,state,'r','metallic',{'viewbox':[32,8]});im=Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=data))).convert('RGB')
  for x,expected in [(2,(0,0)),(6,(204,255)),(12,(102,128)),(20,(0,0)),(26,(204,255)),(30,(0,0))]:
   got=im.getpixel((x,4));self.assertLessEqual(abs(got[0]-expected[0]),1);self.assertLessEqual(abs(got[1]-expected[1]),1)
 def test_numerical_values_and_independent_channels_survive_validation(self):
  p=fixture_project();s=p.initial();l=s['regions']['side']['layers'][-1];l['material']={'metallic':1,'roughness':0};v=p.validate(s);self.assertEqual(v['regions']['side']['layers'][-1]['material'],l['material'])
  for bad in [-.01,1.01,float('nan'),True,'0.5']:
   q=copy.deepcopy(s);q['regions']['side']['layers'][-1]['material']['roughness']=bad
   with self.assertRaises(ValueError):p.validate(q)
 def test_no_override_skips_render(self):
  self.assertIsNone(compose_material('<svg/>',{'regions':{'r':{'layers':[{'id':'a','visible':False,'opacity':1,'material':{'metallic':.9}}]}}},'r','metallic',{'viewbox':[2,2]}))
if __name__=='__main__':unittest.main()
