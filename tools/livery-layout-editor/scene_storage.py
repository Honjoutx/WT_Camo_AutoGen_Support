"""Blender scene storage without changing geometry, UVs or shader values."""
from pathlib import Path
from storage import ContentStore,is_compact,write_json

def save_scene(bpy,output,target):
 output=Path(output);compact=is_compact(output);rows=[];store=ContentStore()
 if compact:
  for image in bpy.data.images:
   if image.source!='FILE':continue  # UDIM / movies retain their original policy.
   if image.packed_file:
    data=bytes(image.packed_file.data);suffix=Path(image.filepath).suffix.lower()
    if data.startswith(b'\x89PNG'):suffix='.png'
    elif data.startswith(b'\xff\xd8\xff'):suffix='.jpg'
    elif data.startswith(b'DDS '):suffix='.dds'
    if not suffix or not suffix[1:].isalnum():suffix='.bin'
    blob,sha=store.put_bytes(data,suffix)
    image.unpack(method='REMOVE');image.filepath=str(blob)
   else:
    source=Path(bpy.path.abspath(image.filepath))
    if not source.is_file():raise FileNotFoundError('预览贴图缺失：'+str(source))
    # Copy external inputs; only this job's generated cache is immutable/adoptable.
    blob,sha,_=store.put_file(source,adopt=source.resolve().is_relative_to(output.resolve()) and source.parent.name in ('textures','materials','planes'))
    image.filepath=str(blob)
   rows.append({'image':image.name,'sha256':sha,'file':str(blob)})
  # Remove unused packed images as well: they would otherwise remain in .blend.
  for image in bpy.data.images:
   if image.source=='FILE':image.filepath=bpy.path.relpath(image.filepath,start=str(Path(target).parent))
 else:
  # A portable scene may be derived from a previous compact scene as well.
  for image in bpy.data.images:
   if image.source=='FILE' and not image.packed_file:image.pack()
 bpy.ops.wm.save_as_mainfile(filepath=str(target),compress=True,relative_remap=not compact)
 if compact:write_json(output/'evidence/scene-storage.json',{'mode':'compact','images':rows,'geometry_and_uv_policy':'unchanged','external_images':True,'project_bundle_required_for_relocation':True})
 return compact
