"""Synthetic layout fixture: never reads user projects or assets."""
from projects import NativeProject

def fixture_project():
 p=object.__new__(NativeProject)
 p.config={'id':'fixture','name':'Fixture','directory':'projects/fixture'}
 p.signature='a'*64;p.compatible_signatures=set()
 p.regions={'side':dict(id='side',viewbox=[96,48],layers=[
  dict(id='node-0',source_id='node-0',index=0,opacity=1,text=None,default_visible=True,default_locked=True),
  dict(id='node-1',source_id='node-1',index=1,opacity=1,text='TEST',default_visible=True,default_locked=False)])}
 return p
