"""Export contract: changed source pixels only, complete design, PNG-only ZIP."""
import hashlib, json, runpy, shutil, subprocess, sys, tempfile, types, unittest, zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from PIL import Image
from texture_bundle import native_images, pack
import native_atlas_export
from native_atlas_export import original_atlas_images


class TextureBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.model = self.root / 'model'
        (self.model / 'textures').mkdir(parents=True)
        (self.model / 'model.blend').touch()
        self.out = self.root / 'job'
        (self.out / 'textures').mkdir(parents=True)
        (self.out / 'materials').mkdir()
        Image.new('RGB', (4, 4), (20, 40, 60)).save(self.model / 'textures/base.png')
        Image.new('RGB', (4, 4), (128, 128, 255)).save(self.model / 'textures/normal.png')
        (self.model / 'repair.json').write_text(json.dumps({'materials': {'original': {
            'map_Kd': 'textures/base.png', 'map_normal': 'textures/normal.png'}}}))
        self.contract = {'model': 'model/model.blend', 'repair_manifest': 'model/repair.json', 'regions': {}}
        self.p = SimpleNamespace(root=self.root, contract=self.contract)
        self.rows = {}

    def domain(self, key, changed=False, compatibility=False):
        self.contract['regions'][key] = {'color_map': 'textures/base.png'}
        row = {'original_texture': 'base.png', 'compatibility_only': compatibility}
        for ch, mode, color in [('color', 'RGB', (20, 40, 60)), ('normal', 'RGB', (128, 128, 255)),
                                ('metallic', 'L', 0), ('roughness', 'L', 153), ('smoothness', 'L', 102), ('height', 'I;16', 0)]:
            path = ('textures/' if ch == 'color' else 'materials/') + key + '-' + ch + '.png'
            image = Image.new(mode, (8, 8), color)
            if changed and ch == 'color':
                image.putpixel((3, 4), (250, 250, 250))
            image.save(self.out / path)
            row[ch] = path
        self.rows[key] = row
        return row

    def test_complete_edited_design_and_exact_unchanged_channels(self):
        # No previous-job comparison: an approved edited domain is always kept.
        edited = self.domain('approved-design', changed=True)
        self.domain('source-only')
        self.domain('obsolete', changed=True, compatibility=True)
        self.domain('unused', changed=True)
        np.save(self.model / 'face-material-domains.npy', np.array(['approved-design', 'source-only', 'obsolete'], dtype=object))
        np.savez(self.model / 'source-bindings.npz', owner=np.array([0, 0, 0]), paint=np.ones(3, bool))
        files, audit = native_images(self.p, self.rows, self.out)
        self.assertEqual(files, [self.out / edited['color']])
        self.assertFalse(audit['approved-design']['channels']['normal']['modified_or_created'])
        before = files[0].read_bytes()
        bundle = pack(self.out, 'final.zip', files, audit)
        with zipfile.ZipFile(bundle) as archive:
            self.assertEqual(archive.namelist(), [Path(edited['color']).name])
            self.assertEqual(archive.read(Path(edited['color']).name), before)
        self.assertTrue((self.out / 'evidence/texture-only-export.json').is_file())

    def test_material_only_edit_is_exported_without_color_or_normal(self):
        row = self.domain('material-only')
        Image.new('L', (8, 8), 240).save(self.out / row['metallic'])
        files, _ = native_images(self.p, self.rows, self.out)
        self.assertEqual(files, [self.out / row['metallic']])

    def test_missing_original_fails_instead_of_exporting_unknown_unchanged_maps(self):
        self.domain('missing')
        (self.model / 'textures/base.png').unlink()
        with self.assertRaises(FileNotFoundError):
            native_images(self.p, self.rows, self.out)

    def test_bundle_rejects_layout_or_model_files(self):
        model = self.out / 'model.blend'
        model.touch()
        with self.assertRaises(ValueError):
            pack(self.out, 'bad.zip', [model])

    def test_domains_merge_into_one_original_filename_and_preserve_unpainted_pixels(self):
        for key, color, limits in [('body-left', (8, 24, 68), (1, 1, 3, 6)),
                                   ('body-right', (240, 245, 250), (4, 1, 6, 6))]:
            row = self.domain(key)
            Image.new('RGB', (8, 8), color).save(self.out / row['color'])
            mask = Image.new('L', (8, 8))
            from PIL import ImageDraw
            ImageDraw.Draw(mask).rectangle(limits, fill=255)
            mask.save(self.model / (key + '.png'))
            self.contract['regions'][key]['mask'] = 'model/' + key + '.png'
        files, audit = original_atlas_images(self.p, self.rows, self.out, size=8)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].relative_to(self.out).as_posix(), 'export/base_Basecolor.png')
        with Image.open(files[0]) as image:
            self.assertEqual(image.getpixel((2, 2)), (8, 24, 68))
            self.assertEqual(image.getpixel((5, 2)), (240, 245, 250))
            self.assertEqual(image.getpixel((0, 0)), (20, 40, 60))
        self.assertEqual(audit['original_color_atlas_count'], 1)
        self.assertEqual(audit['shared_uv_conflict_pixels'], 0)

    def test_shared_uv_uses_same_structural_winner_for_all_channels(self):
        main = self.domain('body-left')
        other = self.domain('components')
        Image.new('RGB', (8, 8), (8, 24, 68)).save(self.out / main['color'])
        Image.new('RGB', (8, 8), (230, 180, 60)).save(self.out / other['color'])
        for row, metal, rough in [(main, 240, 20), (other, 30, 200)]:
            Image.new('L', (8, 8), metal).save(self.out / row['metallic'])
            Image.new('L', (8, 8), rough).save(self.out / row['roughness'])
        files, audit = original_atlas_images(self.p, dict(reversed(list(self.rows.items()))), self.out, 'pbr', size=8)
        self.assertEqual(audit['shared_uv_conflict_pixels'], 64)
        with Image.open(self.out / 'export/base_Basecolor.png') as image:
            self.assertEqual(image.getpixel((3, 3)), (8, 24, 68))
        with Image.open(self.out / 'export/base_Metallic.png') as image:
            self.assertEqual(image.getpixel((3, 3)), 240)
        with Image.open(self.out / 'export/base_Roughness.png') as image:
            self.assertEqual(image.getpixel((3, 3)), 20)
        self.assertEqual(len(files), 3)
        self.assertTrue(all(path.parent == self.out / 'export' for path in files))
        self.assertEqual({path.name for path in files}, {'base_Basecolor.png', 'base_Metallic.png', 'base_Roughness.png'})
        bundle = pack(self.out, 'pbr-flat.zip', files, audit)
        with zipfile.ZipFile(bundle) as archive:
            self.assertEqual(set(archive.namelist()), {path.name for path in files})

    def test_original_shared_normal_filename_is_merged_once(self):
        main = self.domain('body-left')
        other = self.domain('components')
        Image.new('RGB', (4, 4), (30, 70, 10)).save(self.model / 'textures/base2.png')
        other['original_texture'] = 'base2.png'
        self.contract['regions']['components']['color_map'] = 'textures/base2.png'
        repair = json.loads((self.model / 'repair.json').read_text(encoding='utf8'))
        repair['materials']['other'] = {'map_Kd': 'textures/base2.png', 'map_normal': 'textures/normal.png'}
        (self.model / 'repair.json').write_text(json.dumps(repair))
        Image.new('RGB', (8, 8), (8, 24, 68)).save(self.out / main['color'])
        Image.new('RGB', (8, 8), (200, 128, 240)).save(self.out / main['normal'])
        Image.new('RGB', (8, 8), (80, 180, 240)).save(self.out / other['normal'])
        files, _ = original_atlas_images(self.p, self.rows, self.out, 'color-normal', size=8)
        self.assertEqual(len(files), 3)
        self.assertEqual(len(list((self.out / 'export').glob('*_Normal.png'))), 1)
        with Image.open(self.out / 'export/normal_Normal.png') as image:
            self.assertEqual(image.getpixel((2, 2)), (200, 128, 240))

    def test_short_color_and_normal_names_match_checklist_and_zip(self):
        from export_selection import catalogue
        row = self.domain('body-left')
        color = 'vehicle_body_c_us_camo_modern_green.png'
        normal = 'vehicle_body_n.png'
        (self.model / 'textures/base.png').rename(self.model / 'textures' / color)
        (self.model / 'textures/normal.png').rename(self.model / 'textures' / normal)
        row['original_texture'] = color
        row['original_normal'] = normal
        self.contract['regions']['body-left'].update(color_map='textures/' + color, texture_name=color,
                                                     original_normal=normal)
        (self.model / 'repair.json').write_text(json.dumps({'materials': {'original': {
            'map_Kd': 'textures/' + color, 'map_normal': 'textures/' + normal}}}))
        self.p.config = {'type': 'surface-planes', 'models': []}
        Image.new('RGB', (8, 8), (88, 111, 255)).save(self.out / row['color'])
        Image.new('RGB', (8, 8), (140, 128, 250)).save(self.out / row['normal'])
        files, audit = original_atlas_images(self.p, self.rows, self.out, 'color-normal', size=8)
        expected = {'vehicle_body_Basecolor.png', 'vehicle_body_Normal.png'}
        self.assertEqual({p.name for p in files}, expected)
        self.assertEqual({r['filename'] for r in catalogue(self.p, 'color-normal')}, expected)
        with zipfile.ZipFile(pack(self.out, 'short.zip', files, audit)) as archive:
            self.assertEqual(set(archive.namelist()), expected)
        with Image.open(self.out / 'export/vehicle_body_Basecolor.png') as image:
            self.assertEqual(image.getpixel((2, 2)), (88, 111, 255))

    def test_short_names_do_not_overwrite_distinct_original_camo_atlases(self):
        main = self.domain('body-left')
        other = self.domain('components')
        plain, camo = 'tank_c.png', 'tank_c_us_camo_green.png'
        Image.new('RGB', (4, 4), (20, 40, 60)).save(self.model / 'textures' / plain)
        Image.new('RGB', (4, 4), (30, 70, 10)).save(self.model / 'textures' / camo)
        main['original_texture'] = camo
        other['original_texture'] = plain
        Image.new('RGB', (8, 8), (8, 24, 68)).save(self.out / main['color'])
        Image.new('RGB', (8, 8), (230, 180, 60)).save(self.out / other['color'])
        files, _ = original_atlas_images(self.p, self.rows, self.out, 'color', size=8)
        self.assertEqual({p.name for p in files}, {'tank_Basecolor.png', 'tank_2_Basecolor.png'})
        for name, expected in [('tank_Basecolor.png', (8, 24, 68)), ('tank_2_Basecolor.png', (230, 180, 60))]:
            with Image.open(self.out / 'export' / name) as image:
                self.assertEqual(image.getpixel((2, 2)), expected)

    def test_repeated_uv_and_protected_faces_keep_original_coordinates(self):
        row = self.domain('body-left')
        Image.new('RGB', (8, 8), (8, 24, 68)).save(self.out / row['color'])
        uv = np.array([[1.25, .25], [1.75, .25], [1.25, .75]])
        np.savez(self.model / 'source-bindings.npz', owner=np.array([0, 0]), paint=np.array([True, False]),
                 tex=np.array([[0, 1, 2], [0, 1, 2]]), uv_fixed=uv, material_index=np.array([0, 0]))
        np.save(self.model / 'face-material-domains.npy', np.array(['body-left', ''], dtype=object))
        self.contract['regions']['body-left']['repeat'] = True
        before = (self.model / 'source-bindings.npz').read_bytes()
        files, audit = original_atlas_images(self.p, self.rows, self.out, size=8)
        self.assertEqual(files, [])  # all painted pixels are shared with a protected surface
        self.assertGreater(audit['atlases']['base.png']['protected_shared_pixels_restored'], 0)
        self.assertEqual(before, (self.model / 'source-bindings.npz').read_bytes())

    def test_surface_final_worker_packages_pngs_without_starting_blender(self):
        self._run_surface_worker_fixture()

    def test_surface_reuse_without_cached_preview_still_exports(self):
        self._run_surface_worker_fixture(reuse_without_preview=True)

    def _run_surface_worker_fixture(self, reuse_without_preview=False):
        # Exercise the real worker's final-export branch with a tiny bake fixture.
        # Vector raster/bake are fixtures; the pixel filter and ZIP writer are real.
        self.domain('approved-design', changed=True)
        native = self.contract
        surface = {'model': native['model'], 'source_sha256': 'source', 'model_sha256': 'fixture',
                   'capture_bindings': 'capture.npz'}
        (self.root / 'capture.npz').touch()
        source_svg = self.root / 'source.svg'
        source_svg.write_text('<svg/>', encoding='utf-8')
        meta = {'name': 'Fixture plane', 'viewbox': [8, 8],
                'surface': 'real plane', 'source_sha256': hashlib.sha256(source_svg.read_bytes()).hexdigest()}
        p = SimpleNamespace(root=self.root, surface_root=self.root, id='fixture',
            signature='fixture', contract=surface, native_contract=native,
            regions={'plane': meta}, validate=lambda state: state,
            compose=lambda *args, **kw: '<svg/>', source_path=lambda key: source_svg, changed=lambda *args: True)
        state = {'regions': {'plane': {'layers': [
            {'visible': False, 'opacity': 1}, {'visible': True, 'opacity': 1}]}}}
        if reuse_without_preview:
            cache = self.root / 'reuse'
            (cache / 'planes').mkdir(parents=True)
            (cache / 'layout.json').write_text(json.dumps(state))
            cached = {'source_sha256': meta['source_sha256'], 'pixels': [8192, 8192]}
            for ch, mode, color in [('color', 'RGBA', (10, 30, 70, 255)),
                                    ('metallic', 'L', 0), ('roughness', 'L', 153)]:
                name = 'planes/plane-' + ch + '.png'
                Image.new(mode, (8, 8), color).save(cache / name)
                cached[ch] = name
            (cache / 'surface-manifest.json').write_text(json.dumps({
                'project_id': 'fixture', 'model_sha256': 'fixture', 'automatic_material': {}, 'regions': {'plane': cached}}))
            surface['reuse_surface_exports'] = 'reuse/surface-manifest.json'
            original_cached_bytes = (cache / cached['color']).read_bytes()
        for name, value in [('project-config.json', {}), ('layout.json', state),
                            ('job.json', {'id': 'fixture', 'mode': '8k', 'region': 'plane',
                                          'files': [], 'previews': []})]:
            (self.out / name).write_text(json.dumps(value))
        modules = {}
        for name in ['project', 'projects', 'layer_material', 'surface_bake', 'incremental_native']:
            modules[name] = types.ModuleType(name)
        modules['project'].ROOT = self.root
        modules['project'].HERE = Path(__file__).parent
        modules['project'].read = lambda path: json.loads(Path(path).read_text(encoding='utf8'))
        from storage import write_json
        modules['project'].write_json = write_json
        modules['project'].sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
        modules['projects'].ProjectManager = lambda: SimpleNamespace(get=lambda **kw: p)
        modules['layer_material'].compose_material = lambda *args: None
        modules['surface_bake'].bake = lambda *args: self.rows
        modules['incremental_native'].unchanged_domains = lambda *args: ({}, {}, None)
        modules['incremental_native'].link_copy = shutil.copy2
        modules['incremental_native'].registered_domains = lambda project: project.native_contract['regions']
        commands = []
        raster_calls = []
        modules['raster'] = types.ModuleType('raster')
        def svg_fixture(svg, width):
            import io
            raster_calls.append(width)
            stream = io.BytesIO()
            Image.new('RGBA', (8, 8), (10, 30, 70, 255)).save(stream, format='PNG')
            return stream.getvalue()
        modules['raster'].svg_png = svg_fixture

        def raster_fixture(command, **kw):
            commands.append(command)
            self.assertNotIn('blender', str(command[0]).lower())
            Image.new('RGBA', (8, 8), (10, 30, 70, 255)).save(command[-2])
            return SimpleNamespace(returncode=0, stderr=b'')

        with patch.dict(sys.modules, modules), patch.object(subprocess, 'run', raster_fixture), \
                patch.object(native_atlas_export, 'original_atlas_images', lambda project, rows, out, preset, size, update: original_atlas_images(project, rows, out, preset, size=8)), \
                patch.object(sys, 'argv', ['surface_worker.py', '--job', str(self.out)]):
            with self.assertRaises(SystemExit) as ended:
                runpy.run_path(str(Path(__file__).parent / 'surface_worker.py'), run_name='__main__')
            self.assertEqual(ended.exception.code, 0)
        result = json.loads((self.out / 'job.json').read_text(encoding='utf8'))
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['export_policy'], 'original-atlases-only')
        self.assertEqual(result['texture_count'], 1)
        self.assertEqual(len(result['files']), 1)
        self.assertEqual(result['previews'], [])
        self.assertFalse(list(self.out.glob('*.blend')))
        if reuse_without_preview:
            self.assertFalse(commands)  # Reusing approved pixels requires no raster or Blender.
            self.assertFalse(raster_calls)
            self.assertFalse((cache / 'previews/plane.jpg').exists())
            self.assertTrue((self.out / 'previews/plane.jpg').is_file())
            self.assertEqual((cache / cached['color']).read_bytes(), original_cached_bytes)
            report = json.loads((self.out / 'evidence/surface-reuse-audit.json').read_text(encoding='utf8'))
            self.assertTrue(report['plane']['preview_regenerated'])
        else:
            self.assertTrue(raster_calls)
            self.assertFalse(commands)  # PNG export no longer needs a Node/browser subprocess.
        with zipfile.ZipFile(self.out / 'fixture-8k-original-atlases.zip') as archive:
            self.assertEqual(archive.namelist(), ['base_Basecolor.png'])

    def test_flat_archive_rejects_colliding_filenames(self):
        first = self.out / 'textures' / 'same_Basecolor.png'
        second = self.out / 'materials' / 'same_Basecolor.png'
        Image.new('RGB', (4, 4), (10, 20, 30)).save(first)
        Image.new('RGB', (4, 4), (30, 20, 10)).save(second)
        with self.assertRaises(ValueError):
            pack(self.out, 'collision.zip', [first, second])


if __name__ == '__main__':
    unittest.main()
