"""Short game texture names; internal bake paths and source assets stay intact."""
from collections import defaultdict
from pathlib import Path
import re

SUFFIXES = {'color': 'Basecolor', 'metallic': 'Metallic', 'roughness': 'Roughness',
            'smoothness': 'Smoothness', 'normal': 'Normal', 'height': 'Height'}


def atlas_stem(source):
    stem = re.split(r'_(?:c|n)(?:_|$)', Path(source).stem, maxsplit=1, flags=re.I)[0]
    if not stem:
        raise ValueError('Empty texture export stem: ' + str(source))
    return stem


def export_filename(source, channel):
    return atlas_stem(source) + '_' + SUFFIXES[channel] + '.png'


def filename_map(sources):
    """Keep distinct original atlases distinct if their shortened names collide.

    Prefer the qualified camo source for the plain name. A second original atlas
    gets _2 (then _3 etc.), identically in every export mode and the checklist.
    """
    groups = defaultdict(list)
    for source, channel in set(sources):
        groups[export_filename(source, channel).casefold()].append((source, channel))
    used = set(groups)
    result = {}
    for key, entries in sorted(groups.items()):
        entries.sort(key=lambda item: (-len(Path(item[0]).stem), item[0].casefold(), item[0]))
        for index, (source, channel) in enumerate(entries):
            name = export_filename(source, channel)
            if index:
                number = 2
                while True:
                    name = atlas_stem(source) + '_' + str(number) + '_' + SUFFIXES[channel] + '.png'
                    if name.casefold() not in used:
                        break
                    number += 1
            used.add(name.casefold())
            result[source, channel] = name
    return result


def normalize_export_filename(name):
    """Compatibility for saved selections using the former long filenames."""
    if not isinstance(name, str) or '/' in name or '\\' in name or Path(name).name != name:
        raise ValueError('Invalid texture filename')
    stem, separator, suffix = Path(name).stem.rpartition('_')
    suffix = 'Basecolor' if suffix == 'BaseColor' else suffix
    if Path(name).suffix.lower() == '.png' and separator and suffix in SUFFIXES.values():
        return atlas_stem(stem) + '_' + suffix + '.png'
    return name
