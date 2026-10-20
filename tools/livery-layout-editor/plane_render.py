"""Independent, immutable physical-plane render tasks for the export scheduler."""
import io
from pathlib import Path
import numpy as np
from PIL import Image
from export_runtime import save_png


def render(task,rasterizer=None):
    key=task['key'];out=Path(task['out']);width,height=task['pixels']
    cp=out/'planes'/f'{key}-color.png'
    if task['has_art']:
        if rasterizer:rasterizer(task['svg'],width,cp)
        else:
            from raster import svg_png
            cp.write_bytes(svg_png(task['svg'],width))
        with Image.open(cp) as image:color=image.convert('RGBA')
    else:
        color=Image.new('RGBA',(width,height));save_png(color,cp)
    rgb=np.asarray(color.convert('RGB'),np.float32)/255
    foil=np.clip((rgb[:,:,0]-rgb[:,:,2]-.03)*5,0,1);del rgb
    finish=task['finish'];base_m=finish.get('base_metallic',.06);foil_m=finish.get('foil_metallic',.72)
    base_r=finish.get('base_roughness',.40);foil_r=finish.get('foil_roughness',.26)
    scalar={}
    for channel,mat_svg in task['materials'].items():
        automatic=(base_m+(foil_m-base_m)*foil if channel=='metallic' else
                   base_r+(foil_r-base_r)*foil if channel=='roughness' else np.zeros_like(foil))
        if mat_svg and task['has_art']:
            if rasterizer:
                weights=out/'planes'/f'{key}-{channel}-weights.png'
                rasterizer(mat_svg,width,weights)
                with Image.open(weights) as image:im=np.asarray(image.convert('RGB'),np.float32)/255
                weights.unlink()
            else:
                from raster import svg_png
                with Image.open(io.BytesIO(svg_png(mat_svg,width))) as image:im=np.asarray(image.convert('RGB'),np.float32)/255
            value=np.clip(im[:,:,0]+automatic*(1-im[:,:,1]),0,1);del im
        else:value=automatic
        target=out/'planes'/f'{key}-{channel}.png'
        save_png(Image.fromarray(np.uint8(np.rint(value*255))),target)
        scalar[channel]=target.relative_to(out).as_posix()
    pixels=list(color.size);color.thumbnail((450,300));back=Image.new('RGB',color.size,'#183148')
    back.paste(color,mask=color.getchannel('A'));back.save(out/'previews'/f'{key}.jpg',quality=92)
    return dict(color=cp.relative_to(out).as_posix(),**scalar,pixels=pixels,**task['metadata'])
