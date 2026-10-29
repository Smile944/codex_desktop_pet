import json
import tempfile
import unittest
from pathlib import Path
from host import ConfigStore, validated
from scale_policy import adapt_client_scale, adapt_native_scale

ROOT = Path(__file__).resolve().parents[1]


class ScaleTests(unittest.TestCase):
    def test_one_to_one_hundred_percent_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            store = ConfigStore(path)
            for scale in (0.01, 0.02, 0.25, 0.55, 1.0):
                store.update({'scale':scale})
                self.assertEqual(ConfigStore(path).value['scale'], scale)
            for scale in (0, 0.009, 1.01, True):
                with self.assertRaises(ValueError):
                    validated({'scale':scale})

    def test_old_oversize_preference_clamps_without_resetting_other_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'settings.json'
            p.write_text(json.dumps({'scale':1.25,'soundEnabled':False,'bubbleScale':0.95}))
            value = ConfigStore(p).value
            self.assertEqual(value['scale'], 1)
            self.assertFalse(value['soundEnabled'])
            self.assertEqual(value['bubbleScale'], 0.95)

    def test_client_slider_has_one_percent_step_and_bubble_range_unchanged(self):
        source = adapt_client_scale((ROOT / 'lib/client.js').read_text())
        self.assertIn("min: 0.01, max: 1.0, step: 0.01", source)
        self.assertIn("min: 0.8, max: 1.2, step: 0.05", source)
        self.assertNotIn("min: 0.55, max: 1.4", source)

    def test_native_load_save_and_controller_use_new_bounds(self):
        for name in ('LayoutStore.swift', 'PetController.swift'):
            source = adapt_native_scale((ROOT / 'native/macos/Sources' / name).read_text())
            self.assertNotIn('min(1.4, max(0.55,', source)
            self.assertIn('min(1.0, max(0.01,', source)
        source = adapt_native_scale((ROOT / 'native/macos/Sources/PetController.swift').read_text())
        self.assertNotIn('("大", 1.25)', source)


if __name__ == '__main__':
    unittest.main()
