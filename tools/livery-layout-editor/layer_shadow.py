"""Layer drop shadows in canvas space, inside the existing fixed physical clip."""
import math,re,xml.etree.ElementTree as ET
NS='http://www.w3.org/2000/svg'
def defaults():return {'enabled':False,'blur':12.0,'distance':18.0,'angle':135.0,'opacity':.45,'color':'#123845'}
def validate(value):
 if value is None:return defaults()
 if not isinstance(value,dict) or set(value)-set(defaults()):raise ValueError('图层阴影设置无效。')
 result={**defaults(),**value}
 if not isinstance(result['enabled'],bool):raise ValueError('阴影开关应为布尔值。')
 for name,maximum in [('blur',512),('distance',4096),('opacity',1)]:
  number=result[name]
  if isinstance(number,bool) or not isinstance(number,(int,float)) or not math.isfinite(number) or not 0<=number<=maximum:raise ValueError('阴影大小、距离或透明度超出有效范围。')
  result[name]=float(number)
 angle=result['angle']
 if isinstance(angle,bool) or not isinstance(angle,(int,float)) or not math.isfinite(angle) or abs(angle)>360000:raise ValueError('阴影方向无效。')
 result['angle']=float(angle)%360
 if not isinstance(result['color'],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',result['color']):raise ValueError('阴影颜色应为六位十六进制颜色。')
 result['color']=result['color'].lower();return result
def filter_spec(ident,shadow,meta):
 s=validate(shadow);x,y=meta.get('view_origin',[0,0]);w,h=meta['viewbox'];pad=3*s['blur']+s['distance']+2
 angle=math.radians(s['angle']);dx=math.cos(angle)*s['distance'];dy=math.sin(angle)*s['distance']
 attrs={'id':'editor-shadow-'+ident,'filterUnits':'userSpaceOnUse','primitiveUnits':'userSpaceOnUse','x':x-pad,'y':y-pad,'width':w+2*pad,'height':h+2*pad,'color-interpolation-filters':'sRGB'}
 children=[('feGaussianBlur',{'in':'SourceAlpha','stdDeviation':s['blur'],'result':'shadow-blur'}),('feOffset',{'in':'shadow-blur','dx':dx,'dy':dy,'result':'shadow-offset'}),('feFlood',{'flood-color':s['color'],'flood-opacity':s['opacity'],'result':'shadow-color'}),('feComposite',{'in':'shadow-color','in2':'shadow-offset','operator':'in','result':'shadow-only'}),('feMerge',{},[('feMergeNode',{'in':'shadow-only'}),('feMergeNode',{'in':'SourceGraphic'})])]
 return attrs,children
def apply(root,wrapper,layer,meta):
 shadow=validate(layer.get('shadow'))
 if not shadow['enabled'] or not layer['visible'] or layer['opacity']==0:return wrapper
 defs=next((e for e in root if e.tag.rsplit('}',1)[-1]=='defs'),None)
 if defs is None:defs=ET.SubElement(root,f'{{{NS}}}defs')
 attrs,children=filter_spec(layer['id'],shadow,meta);f=ET.SubElement(defs,f'{{{NS}}}filter',{k:str(v) for k,v in attrs.items()})
 for item in children:
  node=ET.SubElement(f,f'{{{NS}}}{item[0]}',{k:str(v) for k,v in item[1].items()})
  if len(item)>2:
   for tag,values in item[2]:ET.SubElement(node,f'{{{NS}}}{tag}',values)
 # Opacity applies once to the complete layer style. Opaque source pixels still
 # cover their own shadow, even when the overall layer is translucent.
 wrapper.set('opacity','1')
 effect=ET.Element(f'{{{NS}}}g',{'id':'shadow-effect-'+layer['id'],'data-layer-shadow':layer['id'],'filter':'url(#'+attrs['id']+')','opacity':str(layer['opacity'])});effect.append(wrapper);return effect
