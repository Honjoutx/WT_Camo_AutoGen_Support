"""Game-facing exports: one image per original atlas, without UV repacking.

Internal material domains are editing/baking documents, not game texture files.
Shared texels cannot display independent artwork on the original model; choose
the main structural document consistently and report that loss of independence.
"""
from collections import defaultdict
from pathlib import Path
import json, re
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from texture_bundle import CHANNELS, DEFAULTS, SUFFIXES, differs, read
from export_naming import export_filename, filename_map

CHANNEL_PRESETS = {'color': ('color',), 'color-normal': ('color', 'normal'),
                   'pbr': CHANNELS}


def priority(key, meta):
    """Prioritize approved large structures over accessories at shared texels."""
    if isinstance(meta.get('export_priority'),int):
        return meta['export_priority']
    if key.startswith(('body-left', 'body-right', 'turret-left', 'turret-right')):
        return 100
    if key.startswith(('body-top', 'turret-top', 'turret-front', 'hull-front', 'front', 'mantlet', 'gun-barrel')):
        return 90
    if key in {'body-main', 'body-armor-a', 'turret-main', 'gun-main', 'turret-armor-a'}:
        return 85
    if meta.get('native_uv_board') or key.startswith('detachable-kit'):
        return 75
    if key.startswith('wheels--'):
        return 65
    return 50


def plan(project, rows):
    contract = getattr(project, 'native_contract', project.contract)
    model = project.root / contract['model']
    repair = read(project.root / contract['repair_manifest'])
    binding_file = model.parent / 'source-bindings.npz'
    bindings = None
    assignment = None
    if binding_file.exists():
        with np.load(binding_file) as archive:
            bindings = {k: archive[k] for k in archive.files}
    assignment_file = model.parent / 'face-material-domains.npy'
    if assignment_file.exists():
        assignment = np.load(assignment_file, allow_pickle=True)
    active = set(assignment[(bindings['owner'] >= 0) & bindings['paint']]) if assignment is not None and bindings is not None else None
    groups = defaultdict(list)
    for key, row in rows.items():
        if row.get('compatibility_only') or (active is not None and key not in active):
            continue
        meta = contract['regions'][key]
        ids = None
        if bindings is not None:
            eligible = (bindings['owner'] >= 0) & bindings['paint']
            if assignment is not None:
                eligible &= assignment == key
            elif meta.get('source_face_ids'):
                eligible &= np.isin(np.arange(len(eligible)), np.load(project.root / meta['source_face_ids']))
            else:
                material_ids = [i for i, material in enumerate(repair['materials'].values()) if material.get('map_Kd') == meta['color_map']]
                eligible &= np.isin(bindings['material_index'], material_ids)
            ids = np.flatnonzero(eligible)
            if not len(ids):
                continue
        groups[row['original_texture']].append((key, row, meta, ids))
    # An explicitly canonical shared atlas is already one image for all aliases.
    # Merge its geometry coverage once, rather than decode the same PBR maps for
    # every historical material domain. Ordinary independent designs keep their
    # existing per-domain priority and conflict reporting.
    for name, domains in list(groups.items()):
        authorities = defaultdict(list)
        ordinary = []
        for domain in domains:
            authority = domain[2].get('atlas_authority')
            if authority:
                authorities[authority].append(domain)
            else:
                ordinary.append(domain)
        for authority, aliases in authorities.items():
            _, row, meta, _ = aliases[0]
            channels = ('color', 'metallic', 'roughness', 'smoothness', 'normal', 'height')
            if any(any(alias[1].get(ch) != row.get(ch) for ch in channels) for alias in aliases):
                raise ValueError('Canonical atlas aliases do not share the same channel images: ' + authority)
            ids = np.unique(np.concatenate([alias[3] for alias in aliases])) if bindings is not None else None
            meta = dict(meta)
            meta.pop('mask', None)
            ordinary.append(('atlas-authority::' + authority, row, meta, ids))
        groups[name] = ordinary
    # Independent of JSON insertion order, export history and input map order.
    for name, domains in groups.items():
        domains.sort(key=lambda domain: (-priority(domain[0], domain[2]), domain[0]))
    return model, repair, bindings, dict(sorted(groups.items()))


def uv_mask(project, meta, ids, bindings, size):
    if bindings is None:
        if not meta.get('mask'):
            return Image.new('L', (size, size), 255)
        with Image.open(project.root / meta['mask']) as image:
            return image.convert('L').resize((size, size), Image.Resampling.NEAREST)
    image = Image.new('L', (size, size))
    draw = ImageDraw.Draw(image)
    for uv in bindings['uv_fixed'][bindings['tex'][ids]]:
        xs = range(int(np.ceil(-uv[:, 0].max())), int(np.floor(1 - uv[:, 0].min())) + 1) if meta.get('repeat') else (0,)
        ys = range(int(np.ceil(-uv[:, 1].max())), int(np.floor(1 - uv[:, 1].min())) + 1) if meta.get('repeat') else (0,)
        for dx in xs:
            for dy in ys:
                draw.polygon([(float((u + dx) * size), float((1 - v - dy) * size)) for u, v in uv], fill=255)
    # Retain sampling padding while staying inside the existing paint contract.
    image = image.filter(ImageFilter.MaxFilter(3))
    if meta.get('mask'):
        with Image.open(project.root / meta['mask']) as allowed:
            a = np.asarray(allowed.convert('L').resize((size, size), Image.Resampling.NEAREST))
        pixels = np.asarray(image).copy()
        pixels[a == 0] = 0
        image = Image.fromarray(pixels)
    return image


def normal_source(name, domains, repair, originals):
    candidates = {row.get('original_normal') for _, row, _, _ in domains if row.get('original_normal')}
    candidates.update(Path(material['map_normal']).name for material in repair['materials'].values()
                      if Path(material.get('map_Kd', '')).name == name and material.get('map_normal'))
    if len(candidates) > 1:
        raise ValueError('An original color atlas has inconsistent normal-map bindings: ' + name)
    path = originals / next(iter(candidates)) if candidates else None
    if path is not None and not path.is_file():
        raise FileNotFoundError(path)
    return path


def resized(path, size, mode):
    with Image.open(path) as image:
        image = image.convert(mode)
        return image.resize((size, size), Image.Resampling.LANCZOS) if image.size != (size, size) else image.copy()


def export_name_map(groups, repair, originals):
    sources = []
    for name, domains in groups.items():
        normal = normal_source(name, domains, repair, originals)
        sources.extend((normal.name if ch == 'normal' and normal else name, ch) for ch in CHANNELS)
    return filename_map(sources)


def merge_group(project, out, name, domains, bindings, repair, originals, size, channels, filenames=None):
    original_color = originals / name
    if not original_color.is_file():
        raise FileNotFoundError(original_color)
    normal = normal_source(name, domains, repair, originals)
    owner = np.full((size, size), -1, dtype=np.int16)
    coverage = np.zeros((size, size), dtype=np.bool_)
    conflicts = np.zeros((size, size), dtype=np.bool_)
    # Resolve once from COLOR, then use the exact same ownership for every PBR
    # channel. Never let an untouched domain's full background erase another.
    baseline = resized(original_color, size, 'RGB')
    merged = baseline.copy()
    contributions = {}
    # Several colour variants share the same original normal atlas. Decode its
    # immutable source once, rather than once per small component domain.
    normal_baselines = {}
    for index, (key, row, meta, ids) in enumerate(domains):
        mask = uv_mask(project, meta, ids, bindings, size)
        pixels = resized(Path(out) / row['color'], size, 'RGB')
        domain_baseline = baseline if row['original_texture'] == name else resized(originals / row['original_texture'], size, 'RGB')
        material_delta = np.zeros((size, size), dtype=np.bool_)
        # Color-only export needs no scalar decoding. PBR ownership also claims
        # material-only edits, then uses that one ownership map for all channels.
        material_channels = ('metallic', 'roughness', 'smoothness', 'height') if channels != ('color',) else ()
        for ch in material_channels:
            if row.get(ch):
                scalar = resized(Path(out) / row[ch], size, 'I;16' if ch == 'height' else 'L')
                material_delta |= np.asarray(scalar) != DEFAULTS[ch]
                del scalar
        if 'normal' in channels and row.get('normal'):
            normal_baseline_path = normal_source(row['original_texture'], [domains[index]], repair, originals)
            baseline_key=str(normal_baseline_path) if normal_baseline_path else None
            if baseline_key not in normal_baselines:
                normal_baselines[baseline_key]=resized(normal_baseline_path, size, 'RGB') if normal_baseline_path else Image.new('RGB', (size, size), DEFAULTS['normal'])
            normal_baseline = normal_baselines[baseline_key]
            normal_pixels = resized(Path(out) / row['normal'], size, 'RGB')
            for y in range(0, size, 256):
                box = (0, y, size, min(size, y + 256))
                material_delta[y:box[3]] |= np.any(np.asarray(normal_pixels.crop(box)) != np.asarray(normal_baseline.crop(box)), axis=2)
            del normal_baseline, normal_pixels
        count = 0
        for y in range(0, size, 256):
            box = (0, y, size, min(size, y + 256))
            occupied = np.asarray(mask.crop(box)) > 0
            color = np.asarray(pixels.crop(box))
            original = np.asarray(domain_baseline.crop(box))
            edited = occupied & np.any(color != original, axis=2)
            # Material-only changes need an owner too, even at original colors.
            edited |= occupied & material_delta[y:box[3]]
            current = np.asarray(merged.crop(box)).copy()
            winners = owner[y:box[3]]
            overlap = edited & (winners >= 0)
            conflicts[y:box[3]] |= overlap & np.any(color != current, axis=2)
            take = edited & (winners < 0)
            current[take] = color[take]
            winners[take] = index
            coverage[y:box[3]] |= edited
            count += int(take.sum())
            merged.paste(Image.fromarray(current), (0, y))
        contributions[key] = count
        del material_delta, mask, pixels, domain_baseline
    protected_pixels = 0
    if bindings is not None:
        color_names = {row['original_texture'] for _, row, _, _ in domains}
        source_ids = [i for i, material in enumerate(repair['materials'].values())
                      if Path(material.get('map_Kd', '')).name in color_names]
        held = np.flatnonzero((bindings['owner'] >= 0) & ~bindings['paint'] &
                             np.isin(bindings['material_index'], source_ids))
        if len(held):
            # Source rubber/contact/other excluded surfaces retain source pixels.
            # Shared pixels cannot simultaneously be painted and unpainted.
            protected = np.asarray(uv_mask(project, {'repeat': any(d[2].get('repeat') for d in domains)}, held, bindings, size)) > 0
            protected_pixels = int((protected & (owner >= 0)).sum())
            for y in range(0, size, 256):
                box = (0, y, size, min(size, y + 256))
                take = protected[y:box[3]]
                a = np.asarray(merged.crop(box)).copy()
                a[take] = np.asarray(baseline.crop(box))[take]
                merged.paste(Image.fromarray(a), (0, y))
                owner[y:box[3]][take] = -1
            del protected
    files = []
    exported = []
    for ch in channels:
        source = original_color if ch == 'color' else normal if ch == 'normal' else None
        mode = 'RGB' if ch in ('color', 'normal') else 'I;16' if ch == 'height' else 'L'
        base = resized(source, size, mode) if source else Image.new(mode, (size, size), DEFAULTS[ch])
        result = merged if ch == 'color' else base.copy()
        if ch != 'color':
            for index, (_, row, _, _) in enumerate(domains):
                if not row.get(ch) or not np.any(owner == index):
                    continue
                incoming = resized(Path(out) / row[ch], size, mode)
                for y in range(0, size, 256):
                    box = (0, y, size, min(size, y + 256))
                    take = owner[y:box[3]] == index
                    if not take.any():
                        continue
                    a = np.asarray(result.crop(box)).copy()
                    a[take] = np.asarray(incoming.crop(box))[take]
                    result.paste(Image.fromarray(a), (0, y))
        raw_name = source.name if ch == 'normal' and source else name
        filename = filenames[raw_name, ch] if filenames is not None else export_filename(raw_name, ch)
        path = Path(out) / 'export' / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            # Multiple original colors can share a normal; never silently replace
            # a second normal with different content under one original name.
            prior = resized(path, size, mode)
            if np.any(np.asarray(prior) != np.asarray(result)):
                raise ValueError('Conflicting merged channels share one original filename: ' + str(path.name))
        else:
            result.save(path)
        if differs(path, source=source, default=DEFAULTS.get(ch)):
            files.append(path)
            exported.append(ch)
        else:
            path.unlink()
    return files, {'source_color': name, 'domains': len(domains), 'resolution': size,
                   'channels': exported, 'shared_uv_conflict_pixels': int(conflicts.sum()),
                   'edited_uv_pixels': int(coverage.sum()), 'protected_shared_pixels_restored': protected_pixels,
                   'chosen_domain_pixels': contributions,
                   'shared_uv_policy': 'Main structure first; one common artwork per original shared texel'}


def original_atlas_images(project, rows, out, preset='color', size=None, update=None):
    if preset not in CHANNEL_PRESETS:
        raise ValueError('Unknown export channel preset')
    model, repair, bindings, groups = plan(project, rows)
    filenames = export_name_map(groups, repair, model.parent / 'textures')
    audit = {'policy': 'One merged image per modified original atlas/channel, native UV unchanged',
             'channel_preset': preset, 'original_color_atlas_count': len(groups), 'atlases': {},
             'file_aliases': {Path(raw).stem + '_' + SUFFIXES[ch] + '.png': filename
                              for (raw, ch), filename in filenames.items()}}
    files = []
    channels = tuple(ch for ch in CHANNEL_PRESETS[preset] if ch != 'normal')
    normals = defaultdict(list)
    for i, (name, domains) in enumerate(groups.items()):
        if update:
            update('合并原始图集 · ' + name, 84 + int(i / max(1, len(groups)) * 13))
        target_size = size or max(row['size'] for _, row, _, _ in domains)
        selected, result = merge_group(project, out, name, domains, bindings, repair,
                                       model.parent / 'textures', target_size, channels, filenames)
        files.extend(selected)
        audit['atlases'][name] = result
        if 'normal' in CHANNEL_PRESETS[preset]:
            source = normal_source(name, domains, repair, model.parent / 'textures')
            normal_key = source.name if source else name + '-normal'
            normals[normal_key].extend(domains)
    # Several camo color variants share ONE original normal-map filename.
    # Merge those domains together before writing that normal, rather than
    # inventing one new normal for each color variant or overwriting duplicates.
    audit['normal_atlases'] = {}
    for normal_key, domains in sorted(normals.items()):
        domains.sort(key=lambda domain: (-priority(domain[0], domain[2]), domain[0]))
        target_size = size or max(row['size'] for _, row, _, _ in domains)
        selected, result = merge_group(project, out, domains[0][1]['original_texture'], domains,
                                       bindings, repair, model.parent / 'textures', target_size, ('normal',), filenames)
        files.extend(selected)
        audit['normal_atlases'][normal_key] = result
    audit['shared_uv_conflict_pixels'] = sum(row['shared_uv_conflict_pixels'] for row in audit['atlases'].values())
    return files, audit
