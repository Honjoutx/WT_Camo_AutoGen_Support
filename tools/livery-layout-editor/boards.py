"""Editable design boards before model-specific face/UV registration."""
from projects import NativeProject
from project import Project,ROOT,read,sha,graphics,layer_info
import copy

class BoardProject(NativeProject):
 def __init__(self,config,library):
  self.config=config;self.root=ROOT/config['directory'];self.state_dir=self.root/'state'
  self.cache=self.root/'cache';self.base=self.root;self.library=library
  self.contract=read(self.root/'model-project.json');self.regions=copy.deepcopy(self.contract['regions'])
  self.signature=sha(self.root/'model-project.json');self.core_signature=self.signature
  self.compatible_signatures=set();self.top={};self.net={'regions':{}}
  for key,meta in self.regions.items():
   meta['layers']=[dict(layer_info(i,e),default_visible=True,default_locked=i==0)
     for i,e in graphics(self.source_root(key))]
   meta['layers'][0].update(label='画布参考 · 只读',kind='base')
   meta.update(source_url=f'/source/{key}.svg',guide_url=f'/guide/{key}.svg',
    thumbnail_url=f'/thumb/{key}.png',reference_url=f'/reference/{key}.png',safe_rect=None)
 def compose(self,state,key):return Project.compose(self,state,key)
