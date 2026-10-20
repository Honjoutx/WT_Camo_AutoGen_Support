"""Export editable plane studies; never presents unbound boards as UV textures."""
from pathlib import Path
import argparse,os,traceback
from project import read,write_json
from projects import ProjectManager
from raster import svg_png
from export_runtime import configure as configure_performance,flush
from storage import register_archive,compact_job

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--job',required=True);args=parser.parse_args()
 folder=Path(args.job).resolve();job=read(folder/'job.json')
 def update(**values):job.update(values);write_json(folder/'job.json',job)
 try:
  configure_performance(job.get('export_performance','max'),folder)
  p=ProjectManager().get(snapshot=read(folder/'project-config.json'));state=p.validate(read(folder/'layout.json'))
  if job['mode']!='boards':raise ValueError('未绑定模型的草图仅支持平面输出。')
  update(status='running',pid=os.getpid(),stage='导出分区草图',progress=5)
  out=folder/'planes';out.mkdir(exist_ok=True);entries=[]
  for i,key in enumerate(p.regions):
   svg=p.compose(state,key);src=out/(key+'.svg');png=out/(key+'.png')
   src.write_text(svg,encoding='utf8');png.write_bytes(svg_png(svg,2048))
   entries.extend([(src,src.relative_to(folder).as_posix()),(png,png.relative_to(folder).as_posix())])
   update(progress=5+int(85*(i+1)/len(p.regions)))
  name=p.id+'-boards.zip';register_archive(folder,name,entries)
  compact_job(folder)
  update(status='complete',stage='分区草图已导出 · 尚未绑定原 UV',progress=100,
   files=[dict(label='分区草图 PNG / SVG',url=f'/job/{job["id"]}/{name}')],
   previews=[dict(label=p.regions[job['region']]['name'],url=f'/job/{job["id"]}/planes/{job["region"]}.png')])
 except Exception as e:
  traceback.print_exc();update(status='failed',stage='草图导出失败',error=str(e))

 finally:flush()
