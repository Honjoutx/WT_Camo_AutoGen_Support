"""Create a small, original vector sandbox. No game assets or historical cases."""
from pathlib import Path
import json,shutil
from runtime import ROOT,APP,render_settings

def write(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')

def sync_skill():
 src=APP/'.agents/skills/wt-camo-workflow'
 # An external workspace also needs repo-scoped CLI skill discovery.
 if not ROOT.is_relative_to(APP) and src.exists():
  shutil.copytree(src,ROOT/'.agents/skills/wt-camo-workflow',dirs_exist_ok=True)

def initialize():
 from raster import svg_png
 sync_skill()
 p=ROOT/'projects/starter';regions={}
 for key,name,group,w,h in [('body-left','车体左侧','车体',2048,700),
   ('body-right','车体右侧','车体',2048,700),('body-top','车体顶部','车体',1200,2048),
   ('turret-left','炮塔左侧','炮塔',1700,700),('turret-right','炮塔右侧','炮塔',1700,700),
   ('turret-top','炮塔顶部','炮塔',1200,1400),('front','首上','车体',1400,850)]:
  svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<rect id="reference" width="{w}" height="{h}" fill="#eef1f4"/>
<rect id="base-color" data-layer-label="底色 · 可编辑" width="{w}" height="{h}" fill="#142334"/>
<g id="macro-flow" data-layer-label="草图 · 大色块与走向"><path d="M0 {h*.1} Q{w*.4} {h*.2} {w*.6} {h} H0Z" fill="#dfe8ec"/><path d="M{w*.1} 0Q{w*.5} {h*.3} {w*.7} {h}" fill="none" stroke="#d9b671" stroke-width="6"/></g>
<g id="detail" data-layer-label="草图 · 局部细节" fill="none" stroke="#7a98ae" stroke-width="2"><circle cx="{w*.8}" cy="{h*.55}" r="{min(w,h)*.27}"/><path d="M{w*.69} {h*.55}H{w*.91}M{w*.8} {h*.3}V{h*.8}"/></g>
<text id="title" data-layer-label="草图 · 标题" x="{w*.08}" y="{h*.65}" font-family="sans-serif" font-size="{min(w,h)*.09}" fill="#18334b">DESIGN STUDY</text></svg>'''
  for d in ['sources','guides','previews','state','assets/imported']:(p/d).mkdir(parents=True,exist_ok=True)
  (p/'sources'/f'{key}-editable.svg').write_text(svg,encoding='utf8')
  guide=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"><rect x="12" y="12" width="{w-24}" height="{h-24}" fill="none" stroke="#e2b56e" stroke-dasharray="14 10" stroke-width="3"/></svg>'
  (p/'guides'/f'{key}.svg').write_text(guide,encoding='utf8')
  png=svg_png(svg,420)
  (p/'previews'/f'{key}.png').write_bytes(png)
  regions[key]=dict(id=key,name=name,group=group,viewbox=[w,h],pixels=[w,h],description='布局草图示例；尚未与实际模型表面和原 UV 绑定。')
 write(p/'model-project.json',dict(schema='livery-boards/v1',regions=regions))
 write(p/'state/render-settings.json',render_settings())
 registry=dict(schema='livery-projects/v1',active_project='starter',projects={'starter':dict(id='starter',name='新设计 · 分区草图',type='boards',directory='projects/starter',models=[],shared_library='common',description='先完成设计草图，再建立真实模型平面和 UV 绑定。')},libraries={'common':dict(id='common',name='共享素材库',roots=[],imports='assets/shared/imported')})
 write(ROOT/'projects/registry.json',registry)
 return registry

if __name__=='__main__':
 sync_skill()
 if not (ROOT/'projects/registry.json').exists():initialize()
 print(ROOT)
