"""Match game-facing PNGs to source material names for honest UV previews."""
from pathlib import Path
from project import read,write_json

SUFFIX={'color':'Basecolor','metallic':'Metallic','roughness':'Roughness','normal':'Normal'}

def write_manifest(project,out,audit):
 out=Path(out);native=getattr(project,'native_contract',project.contract)
 repair=read(project.root/native['repair_manifest']);rows={};aliases=audit['file_aliases']
 for texture in audit['atlases']:
  normal=next((Path(m['map_normal']).name for m in repair['materials'].values() if Path(m.get('map_Kd','')).name==texture and m.get('map_normal')),None)
  row={}
  for channel,suffix in SUFFIX.items():
   source=normal if channel=='normal' else texture
   if not source:continue
   filename=aliases.get(Path(source).stem+'_'+suffix+'.png')
   if filename and (out/'export'/filename).is_file():row[channel]='export/'+filename
  rows[texture]=row
 report=dict(schema='original-uv-preview/v1',materials=rows,policy='Exactly the merged game PNGs, one artwork per original shared UV texel')
 write_json(out/'game-atlas-manifest.json',report);return report
