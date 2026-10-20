"""One canonical image for material domains that share original atlas texels."""
import copy,json
from pathlib import Path
import numpy as np
from PIL import Image
from export_runtime import save_png
from project import read,write_json,sha

def bake_authorities(project,planes,out,size,update,bake):
    domains=project.native_contract['regions'];groups={};ordinary={}
    for key,meta in domains.items():
        authority=meta.get('atlas_authority')
        if authority:groups.setdefault(authority,{})[key]=meta
        else:ordinary[key]=meta
    rows={};audits={};original_native=project.native_contract
    try:
        if ordinary:
            project.native_contract={**original_native,'regions':ordinary}
            rows.update(bake(project,planes,out,size,update))
            audits.update(read(out/'evidence/surface-bake-audit.json'))
        for name,members in groups.items():
            spec=project.contract['atlas_authorities'][name];key=spec['bake_key']
            meta=copy.deepcopy(next(iter(members.values())))
            meta.pop('atlas_authority',None);meta.update(id=key,name=spec['name'],source_face_ids=spec['source_face_ids'],mapping_face_ids=spec['mapping_face_ids'],mask=spec['mask'],fallback_fill=spec['fallback_fill'],surface_alpha_floor=0,minimum_export_size=spec.get('minimum_export_size',0))
            if spec.get('material_mask'):
                meta['mask']=spec['material_mask']
                meta['mapping_mask_sha256']=sha(project.root/meta['mask'])
            project.native_contract={**original_native,'regions':{key:meta}}
            row=bake(project,planes,out,size,update)[key]
            audit=read(out/'evidence/surface-bake-audit.json')[key]
            # Keep the accepted game atlas outside this explicitly scoped UV mask.
            with Image.open(project.root/spec['mask']) as image:mask=np.asarray(image.convert('L').resize((row['size'],row['size']),Image.Resampling.NEAREST))>0
            with Image.open(project.root/meta['mask']) as image:material_mask=np.asarray(image.convert('L').resize((row['size'],row['size']),Image.Resampling.NEAREST))>0
            for channel,reference in spec.get('baseline_channels',{}).items():
                if not row.get(channel):continue
                path=out/row[channel]
                with Image.open(path) as image:mode=image.mode;pixels=np.asarray(image).copy()
                with Image.open(project.root/reference) as image:prior=np.asarray(image.convert(mode).resize((row['size'],row['size']),Image.Resampling.LANCZOS))
                channel_mask=material_mask if channel in ['metallic','roughness','smoothness'] else mask
                pixels[~channel_mask]=prior[~channel_mask];save_png(Image.fromarray(pixels),path)
            row['sha256']=sha(out/row['color'])
            for domain,config in members.items():
                rows[domain]={**row,'source_face_ids':config.get('source_face_ids'),'atlas_authority':name}
                audits[domain]={**audit,'canonical_original_atlas':True,'all_aliases_same_png':True,'protected_prior_atlas_pixels_exact':True}
    finally:project.native_contract=original_native
    write_json(out/'evidence/surface-bake-audit.json',audits)
    return rows
