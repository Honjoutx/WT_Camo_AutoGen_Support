"""User-facing original PNG filenames, never internal material-domain files."""
from pathlib import Path
import json
from texture_bundle import SUFFIXES
from export_naming import atlas_stem,normalize_export_filename
from native_atlas_export import CHANNEL_PRESETS,plan,normal_source,export_name_map

def catalogue(project,preset):
 if preset not in CHANNEL_PRESETS:raise ValueError('贴图通道选项无效。')
 if project.config['type']=='boards':return []
 from project import ROOT,read
 contract=getattr(project,'native_contract',project.contract);model=project.root/contract['model']
 # A saved preview scene can predate newly registered paint domains. The file
 # selector must describe the active contract that the worker will bake.
 rows={k:dict(original_texture=m['texture_name'],original_normal=m.get('original_normal'),compatibility_only=m.get('compatibility_only',False)) for k,m in contract['regions'].items()}
 _,repair,bindings,groups=plan(project,rows);files={}
 filenames=export_name_map(groups,repair,model.parent/'textures')
 for name,domains in groups.items():
  for channel in CHANNEL_PRESETS[preset]:
   source=normal_source(name,domains,repair,model.parent/'textures') if channel=='normal' else None
   raw=source.name if source else name;filename=filenames[raw,channel]
   files[filename]=dict(filename=filename,channel=SUFFIXES[channel],atlas=atlas_stem(name),original_filename=Path(raw).stem+'_'+SUFFIXES[channel]+'.png')
 return [files[n] for n in sorted(files)]

def validate_selection(requested,available):
 if requested is None:return None
 if not isinstance(requested,list) or not requested or len(requested)>1000:raise ValueError('请至少选择一个贴图文件。')
 allowed={row['filename'] for row in available}
 aliases={row.get('original_filename',row['filename']):row['filename'] for row in available}
 clean=[aliases.get(n,normalize_export_filename(n)) for n in requested]
 if any(n not in allowed for n in clean):raise ValueError('勾选的贴图文件不属于当前项目或通道方案。')
 return sorted(set(clean))


def selected_domains(project,requested,preset):
 """Prune whole unrequested atlases, retaining every shared-texel contributor.

 Compute names on the complete contract first: shortening filename collisions
 must never depend on which images the user happened to select.
 """
 if requested is None:return None
 contract=getattr(project,'native_contract',project.contract)
 rows={k:dict(original_texture=m['texture_name'],original_normal=m.get('original_normal'),compatibility_only=m.get('compatibility_only',False)) for k,m in contract['regions'].items()}
 model,repair,_,groups=plan(project,rows);originals=model.parent/'textures'
 filenames=export_name_map(groups,repair,originals)
 aliases={Path(raw).stem+'_'+SUFFIXES[ch]+'.png':filename for (raw,ch),filename in filenames.items()}
 want={aliases.get(n,normalize_export_filename(n)) for n in requested};keys=set();authorities=set()
 for name,domains in groups.items():
  normal=normal_source(name,domains,repair,originals)
  if not any(filenames[normal.name if ch=='normal' and normal else name,ch] in want for ch in CHANNEL_PRESETS[preset]):continue
  for key,_,meta,_ in domains:
   if meta.get('atlas_authority'):authorities.add(meta['atlas_authority'])
   else:keys.add(key)
 keys.update(k for k,m in contract['regions'].items() if m.get('atlas_authority') in authorities)
 return dict(keys=keys,filenames=filenames,total_atlases=len(groups))

def select_images(images,requested,out,audit=None):
 if requested is None:return images
 if not isinstance(requested,list) or not requested or any(not isinstance(n,str) or Path(n).name!=n or '/' in n or '\\' in n for n in requested):raise ValueError('贴图文件选择无效。')
 aliases=(audit or {}).get('file_aliases',{});want={aliases.get(n,normalize_export_filename(n)) for n in requested};selected=[p for p in images if Path(p).name in want];skipped=[p for p in images if Path(p).name not in want]
 if not selected:raise ValueError('勾选的文件没有已修改贴图可导出，请选择其他文件。')
 root=(Path(out)/'export').resolve()
 for p in skipped:
  path=Path(p).resolve()
  if not path.is_relative_to(root):raise ValueError('导出文件不在当前任务的 export 目录中。')
  path.unlink()
 evidence=dict(requested=requested,exported=[Path(p).name for p in selected],omitted=[Path(p).name for p in skipped],unchanged_or_unavailable=sorted(want-{Path(p).name for p in images}))
 from project import write_json
 write_json(Path(out)/'evidence/export-file-selection.json',evidence)
 if audit is not None:audit['file_selection']=evidence
 return selected
