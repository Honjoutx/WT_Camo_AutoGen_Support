import unittest,copy,sys,io,xml.etree.ElementTree as ET,subprocess,json
from pathlib import Path
H=Path(__file__).resolve().parent;R=H.parents[1];
import resvg_py
from PIL import Image
import layer_shadow as SH
from project import tag,NS
from test_helpers import fixture_project
import shutil
from layer_material import compose_material
def drawing(shadow=None,opacity=1,transform=None,clip=96):
 root=ET.fromstring(f'<svg xmlns="{NS}" width="96" height="48" viewBox="0 0 96 48"><defs><clipPath id="physical"><rect width="{clip}" height="48"/></clipPath></defs></svg>');outer=ET.Element(f'{{{NS}}}g',{'clip-path':'url(#physical)'})
 wrapper=ET.Element(f'{{{NS}}}g',{'id':'layout-one','opacity':str(opacity)})
 if transform:wrapper.set('transform',transform)
 ET.SubElement(wrapper,f'{{{NS}}}path',{'d':'M10 8h8v8h-8zM10 26h8v8h-8z','fill':'#ff6600'})
 layer={'id':'one','visible':True,'opacity':opacity,'shadow':{**SH.defaults(),'enabled':True,'blur':0,'distance':20,'angle':0,'color':'#123845','opacity':.6,**(shadow or {})},'material':{'metallic':.8}}
 outer.append(SH.apply(root,wrapper,layer,{'viewbox':[96,48]}));root.append(outer);return ET.tostring(root,encoding='unicode'),layer
def raster(svg):return Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert('RGBA')
class ShadowTests(unittest.TestCase):
 def test_silhouette_holes_and_opaque_source_color_preserved(self):
  svg,_=drawing();im=raster(svg);self.assertEqual(im.getpixel((13,11)),(255,102,0,255));self.assertEqual(im.getpixel((33,22))[3],0)
  pixel=im.getpixel((33,11));self.assertGreater(pixel[3],150);self.assertLessEqual(max(abs(a-b) for a,b in zip(pixel[:3],(18,56,69))),2)
 def test_layer_opacity_applies_once_to_shadow_and_foreground(self):
  svg,_=drawing(opacity=.5);im=raster(svg);self.assertLessEqual(abs(im.getpixel((13,11))[3]-128),1);self.assertLessEqual(abs(im.getpixel((33,11))[3]-77),1)
 def test_canvas_direction_survives_rotation_and_flip(self):
  svg,_=drawing(transform='translate(28 0) rotate(90 14 12) scale(-1 1) translate(-28 0)');root=ET.fromstring(svg);offset=next(e for e in root.iter() if tag(e)=='feOffset');self.assertAlmostEqual(float(offset.get('dx')),20);self.assertAlmostEqual(float(offset.get('dy')),0)
  # Reordering transform/clip must keep the filter outside the art transform.
  effect=next(e for e in root.iter() if e.get('data-layer-shadow'));self.assertNotIn('transform',effect.attrib);self.assertIn('transform',next(iter(effect)).attrib)
 def test_fixed_clip_and_softness_size(self):
  svg,_=drawing(clip=29);im=raster(svg);self.assertEqual(im.getpixel((33,11))[3],0)
  sharp,_=drawing();soft,_=drawing({'blur':4});a,b=raster(sharp),raster(soft);self.assertEqual(a.getpixel((28,11))[3],0);self.assertGreater(b.getpixel((28,11))[3],0);self.assertLess(b.getpixel((33,11))[3],a.getpixel((33,11))[3])
 def test_material_override_uses_effect_alpha(self):
  svg,l=drawing({'opacity':.5},opacity=.5);state={'regions':{'test':{'layers':[l]}}};data=compose_material(svg,state,'test','metallic',{'viewbox':[96,48]});im=raster(data)
  for xy,expected in [((13,11),(102,128)),((33,11),(51,64)),((33,22),(0,0))]:
   got=im.getpixel(xy);self.assertLessEqual(abs(got[0]-expected[0]),1);self.assertLessEqual(abs(got[1]-expected[1]),1)
 def test_validation_and_current_draft_are_lossless(self):
  p=fixture_project();s=p.initial();self.assertEqual(p.validate(s),s)
  l=s['regions']['side']['layers'][-1];l['shadow']={**SH.defaults(),'enabled':True,'angle':-90,'blur':0,'distance':42,'color':'#FF0000'};new=p.validate(s)['regions']['side']['layers'][-1];self.assertEqual(new['shadow']['angle'],270);self.assertEqual(new['shadow']['color'],'#ff0000')
  for name,value in [('enabled',1),('blur',-1),('blur',513),('distance',4097),('opacity',1.1),('angle',float('nan')),('color','red'),('color','url(#x)'),('blur',True)]:
   with self.subTest(name=name,value=value):
    with self.assertRaises(ValueError):SH.validate({name:value})
 @unittest.skipUnless(shutil.which('node'),'Node is optional')
 def test_js_python_geometry_defaults_agree(self):
  shadow={**SH.defaults(),'enabled':True,'blur':31,'angle':237,'distance':52};meta={'viewbox':[3456,2432],'view_origin':[-192,-896]};args=json.dumps([shadow,meta]);code="const s=require('./web/shadow.js');const [v,m]=JSON.parse(process.argv[1]);process.stdout.write(JSON.stringify({defaults:s.defaults(),spec:s.spec('one',v,m)}));";j=json.loads(subprocess.check_output([shutil.which('node'),'-e',code,args],cwd=H));self.assertEqual(j['defaults'],SH.defaults());attrs,children=SH.filter_spec('one',shadow,meta);self.assertEqual(j['spec']['attrs'],attrs)
  for name in ['dx','dy']:self.assertAlmostEqual(j['spec']['children'][1][1][name],children[1][1][name])
if __name__=='__main__':unittest.main()
