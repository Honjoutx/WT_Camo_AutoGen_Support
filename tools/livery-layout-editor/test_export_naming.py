import unittest
from export_naming import export_filename, filename_map, normalize_export_filename


class ExportNamingTests(unittest.TestCase):
    def test_requested_names_for_every_channel(self):
        raw = 'vehicle_body_c_us_camo_modern_green.jpg'
        for channel, suffix in [('color', 'Basecolor'), ('metallic', 'Metallic'),
                                ('roughness', 'Roughness'), ('smoothness', 'Smoothness'),
                                ('height', 'Height')]:
            self.assertEqual(export_filename(raw, channel), 'vehicle_body_' + suffix + '.png')
        self.assertEqual(export_filename('vehicle_body_n.jpg', 'normal'), 'vehicle_body_Normal.png')

    def test_only_complete_channel_marker_tokens_are_removed(self):
        self.assertEqual(export_filename('tank_canopy_navy.jpg', 'color'), 'tank_canopy_navy_Basecolor.png')
        self.assertEqual(export_filename('smooth_barrel_a_c_smooth_barrel_a_c.jpg', 'color'), 'smooth_barrel_a_Basecolor.png')
        self.assertEqual(export_filename('chain_a_c.jpg', 'color'), 'chain_a_Basecolor.png')
        self.assertEqual(export_filename('net_f_c.jpg', 'color'), 'net_f_Basecolor.png')

    def test_colliding_originals_remain_distinct_and_order_independent(self):
        sources = [(name, channel) for name in ['tank_c.jpg', 'tank_c_us_camo_green.jpg', 'tank_2_c.jpg']
                   for channel in ['color', 'metallic', 'normal']]
        names = filename_map(sources)
        self.assertEqual(names, filename_map(reversed(sources)))
        self.assertEqual(names['tank_c_us_camo_green.jpg', 'color'], 'tank_Basecolor.png')
        self.assertEqual(names['tank_c.jpg', 'color'], 'tank_3_Basecolor.png')
        self.assertEqual(names['tank_2_c.jpg', 'color'], 'tank_2_Basecolor.png')
        self.assertEqual(len(set(names.values())), len(sources))

    def test_old_selection_normalization_and_path_rejection(self):
        self.assertEqual(normalize_export_filename('tank_c_us_camo_green_Basecolor.png'), 'tank_Basecolor.png')
        self.assertEqual(normalize_export_filename('tank_n_Normal.png'), 'tank_Normal.png')
        self.assertEqual(normalize_export_filename('tank_2_Normal.png'), 'tank_2_Normal.png')
        for name in ['../tank_Normal.png', 'folder\\tank_Normal.png', {}, 42]:
            with self.assertRaises(ValueError):
                normalize_export_filename(name)


if __name__ == '__main__':
    unittest.main()
