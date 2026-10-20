"""Apply native atlas images and render a derived model scene using GPU Cycles."""
import bpy,sys,json,math
import numpy as np
from pathlib import Path
from mathutils import Vector
args=sys.argv[sys.argv.index('--')+1:];O=Path(args[0]);model=Path(args[1]);mode=args[2];manifest=json.loads((O/'manifest.json').read_text(encoding='utf8'));bpy.ops.wm.open_mainfile(filepath=str(model));sc=bpy.context.scene
sys.path.insert(0,str(Path(__file__).resolve().parent));import gpu_bootstrap
gpu_bootstrap.configure('native-preview')
from scene_storage import save_scene
from storage import is_compact
compact=is_compact(O)
def snapshot():
 return {o.name:{'positions':np.array([v.co for v in o.data.vertices]),'faces':np.array([f.vertices for f in o.data.polygons]),'normals':np.array([v.vector for v in o.data.corner_normals]),'uv':{uv.name:np.array([v.uv for v in uv.data]) for uv in o.data.uv_layers}} for o in bpy.data.objects if o.type=='MESH'}
before=snapshot()
game_manifest=json.loads((O/'game-atlas-manifest.json').read_text(encoding='utf8')) if (O/'game-atlas-manifest.json').is_file() else None
for mat in bpy.data.materials:
 key=mat.get('color_domain');row=manifest['regions'].get(key)
 if game_manifest and mat.use_nodes:
  source_texture=row.get('original_texture') if row else None
  if not source_texture and mat.get('source_mtl_recipe'):
   recipe=json.loads(mat['source_mtl_recipe']);source_texture=Path(recipe.get('map_Kd','')).name
  color_node=next((n for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.label=='map_Kd' and n.image),None)
  if not source_texture and color_node:source_texture=Path(color_node.image.filepath).name
  row=game_manifest['materials'].get(source_texture)
 if not row or not mat.use_nodes:continue
 nt=mat.node_tree;bs=next(n for n in nt.nodes if n.type=='BSDF_PRINCIPLED')
 bs.inputs['Specular IOR Level'].default_value=.23
 for node in nt.nodes:
  if row.get('color') and node.type=='TEX_IMAGE' and node.label=='map_Kd':node.image=bpy.data.images.load(str(O/row['color']),check_existing=True);node.image.pack()
 for channel,socket in [('metallic','Metallic'),('roughness','Roughness')]:
  if not row.get(channel):continue
  node=nt.nodes.new('ShaderNodeTexImage');node.image=bpy.data.images.load(str(O/row[channel]),check_existing=True);node.image.colorspace_settings.name='Non-Color';node.image.pack();nt.links.new(node.outputs['Color'],bs.inputs[socket])
 if row.get('normal'):
  node=nt.nodes.new('ShaderNodeTexImage');node.label='Original detail + layer paint relief';node.image=bpy.data.images.load(str(O/row['normal']),check_existing=True);node.image.colorspace_settings.name='Non-Color';node.image.pack();normal=nt.nodes.new('ShaderNodeNormalMap');normal.label='Livery tangent normal · OpenGL +Y';nt.links.new(node.outputs['Color'],normal.inputs['Color']);nt.links.new(normal.outputs['Normal'],bs.inputs['Normal'])
sc['layout_manifest']=str(O/'manifest.json');save_scene(bpy,O,O/'Layout_Working.blend')
bpy.ops.wm.open_mainfile(filepath=str(O/'Layout_Working.blend'));after=snapshot()
assert set(before)==set(after)
for name,row in before.items():
 for field in ['positions','faces','normals']:assert np.array_equal(row[field],after[name][field]),(name,field)
 assert set(row['uv'])==set(after[name]['uv'])
 for field in row['uv']:assert np.array_equal(row['uv'][field],after[name]['uv'][field]),(name,field)
if compact:assert all(not im.packed_file and Path(bpy.path.abspath(im.filepath)).is_file() for im in bpy.data.images if im.source=='FILE')
else:assert all(im.packed_file for im in bpy.data.images if im.source=='FILE')
(O/'evidence/model-integrity.json').write_text(json.dumps(dict(reopened=True,original_geometry_exact=True,original_all_UV_layers_exact=True,original_corner_normals_exact=True,images_packed=not compact,external_images=compact)),encoding='utf8');sc=bpy.context.scene
if mode=='preview':
 sc.render.engine='CYCLES';gpu_bootstrap.configure('preview');sc.cycles.samples=gpu_bootstrap.SETTINGS.get('samples',64);sc.cycles.use_denoising=True;sc.render.resolution_x=1500;sc.render.resolution_y=1000;sc.render.resolution_percentage=100;sc.render.image_settings.file_format='PNG';sc.view_settings.view_transform='AgX'
 sc.world=bpy.data.worlds.new('Preview neutral world');sc.world.use_nodes=True;nt=sc.world.node_tree;nt.nodes.clear();bg=nt.nodes.new('ShaderNodeBackground');world_out=nt.nodes.new('ShaderNodeOutputWorld');bg.inputs[0].default_value=(.24,.27,.32,1);bg.inputs[1].default_value=.45;nt.links.new(bg.outputs[0],world_out.inputs['Surface'])
 cam=bpy.data.objects.new('PreviewCamera',bpy.data.cameras.new('PreviewCamera'));sc.collection.objects.link(cam);sc.camera=cam;cam.data.type='ORTHO';cam.data.ortho_scale=12;cam.location=(8,-12,8);cam.rotation_euler=(Vector((0,0,1.6))-cam.location).to_track_quat('-Z','Y').to_euler()
 for i,(pos,power) in enumerate([((5,-7,10),1600),((-5,4,8),1900)]):
  light=bpy.data.lights.new('PreviewArea'+str(i),'AREA');light.energy=power;light.size=7;ob=bpy.data.objects.new(light.name,light);sc.collection.objects.link(ob);ob.location=pos;ob.rotation_euler=(Vector((0,0,1.5))-ob.location).to_track_quat('-Z','Y').to_euler()
 sc.render.filepath=str(O/'previews/model.png');bpy.ops.render.render(write_still=True)
