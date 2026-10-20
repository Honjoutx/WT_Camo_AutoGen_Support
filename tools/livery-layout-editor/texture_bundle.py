"""Final export contains edited native PNGs, compared with source map pixels.

Previous exports are cache inputs, never the change baseline: an unchanged
approved design still belongs in a final export if it differs from the original.
Work files and provenance stay in the job directory, outside the download ZIP.
"""
from pathlib import Path
import json, zipfile
import numpy as np
from PIL import Image
from export_naming import SUFFIXES
from storage import register_archive

FINAL_MODES = {'4k', '8k'}
CHANNELS = ('color', 'metallic', 'roughness', 'smoothness', 'normal', 'height')
DEFAULTS = {'metallic': 0, 'roughness': 153, 'smoothness': 102,
            'normal': (128, 128, 255), 'height': 0}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def differs(path, source=None, default=None):
    """Match the bake's Lanczos source baseline; bound comparison array memory."""
    with Image.open(path) as exported:
        mode = 'RGBA' if exported.mode == 'RGBA' else 'RGB' if exported.mode == 'RGB' else exported.mode
        actual = exported.convert(mode)
        baseline = None
        if source is not None:
            with Image.open(source) as original:
                baseline = original.convert(mode).resize(actual.size, Image.Resampling.LANCZOS)
        elif default is None:
            raise ValueError('Missing source pixel baseline: ' + str(path))
        for y in range(0, actual.height, 256):
            box = (0, y, actual.width, min(y + 256, actual.height))
            pixels = np.asarray(actual.crop(box))
            expected = np.asarray(baseline.crop(box)) if baseline is not None else default
            if np.any(pixels != expected):
                return True
    return False


def image_differs(actual,baseline=None,default=None):
    """Same exact comparison on decoded pixels, before writing a new PNG."""
    if baseline is None and default is None:raise ValueError('Missing image baseline')
    for y in range(0,actual.height,256):
        box=(0,y,actual.width,min(y+256,actual.height))
        expected=np.asarray(baseline.crop(box)) if baseline is not None else default
        if np.any(np.asarray(actual.crop(box))!=expected):return True
    return False


def native_images(project, rows, out):
    """Select actually used domains and channels; retain existing PNG payloads."""
    out = Path(out)
    contract = getattr(project, 'native_contract', project.contract)
    model = project.root / contract['model']
    originals = model.parent / 'textures'
    assignment_path = model.parent / 'face-material-domains.npy'
    binding_path = model.parent / 'source-bindings.npz'
    active = None
    if assignment_path.exists() and binding_path.exists():
        assignments = np.load(assignment_path, allow_pickle=True)
        with np.load(binding_path) as bindings:
            active = set(assignments[(bindings['owner'] >= 0) & bindings['paint']])
    repair_path = project.root / contract['repair_manifest']
    materials = read(repair_path)['materials'].values()
    selected, audit = [], {}
    for key, row in rows.items():
        meta = contract['regions'][key]
        if (active is not None and key not in active) or row.get('compatibility_only'):
            audit[key] = {'excluded': 'unused compatibility domain'}
            continue
        original_color = originals / row['original_texture']
        if not original_color.is_file():
            raise FileNotFoundError('Original color map required to filter final export: ' + str(original_color))
        normal_name = row.get('original_normal') or next(
            (m.get('map_normal') for m in materials
             if m.get('map_Kd') == meta['color_map'] and m.get('map_normal')), None)
        original_normal = originals / Path(normal_name).name if normal_name else None
        if original_normal is not None and not original_normal.is_file():
            raise FileNotFoundError('Original normal map missing: ' + str(original_normal))
        channels = {}
        for channel in CHANNELS:
            if not row.get(channel):
                continue
            path = out / row[channel]
            source = original_color if channel == 'color' else original_normal if channel == 'normal' else None
            changed = differs(path, source=source, default=DEFAULTS.get(channel))
            channels[channel] = {'file': row[channel], 'modified_or_created': changed}
            if changed:
                selected.append(path)
        audit[key] = {'original_texture': row['original_texture'], 'channels': channels}
    return selected, audit


def pack(out, name, images, audit=None):
    """No models, original assets, SVGs or JSON records in the final download."""
    out = Path(out).resolve()
    images = sorted({Path(p).resolve() for p in images})
    for path in images:
        if not path.is_relative_to(out) or path.suffix.lower() != '.png' or not path.is_file():
            raise ValueError('Final bundle accepts only PNGs from this job: ' + str(path))
    names = [path.name.casefold() for path in images]
    if len(names) != len(set(names)):
        raise ValueError('Duplicate filenames in flat texture export')
    bundle = register_archive(out, name, [(path,path.name) for path in images], zipfile.ZIP_STORED)
    evidence = out / 'evidence' / 'texture-only-export.json'
    evidence.parent.mkdir(exist_ok=True)
    evidence.write_text(json.dumps({
        'policy': (audit or {}).get('policy', 'Only modified or newly authored native PNG channels; source pixels are the baseline'),
        'png_count': len(images), 'bundle': name,
        'files': [p.relative_to(out).as_posix() for p in images],
        'domains': audit or {}, 'no_model_or_layout_in_bundle': True,
        'flat_archive': True
    }, ensure_ascii=False, indent=2), encoding='utf8')
    return bundle
