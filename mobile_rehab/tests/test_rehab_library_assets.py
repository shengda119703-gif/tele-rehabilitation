"""Public action illustrations are content, never measurement/phase bindings."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class LibraryAssetsTest(unittest.TestCase):
    def test_pack_contains_all_cards_and_only_selected_public_images(self):
        spec = importlib.util.spec_from_file_location('library_assets', ROOT/'tools/build_rehab_library_assets.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            result = module.build(Path(folder))
            self.assertEqual(len(result['actions']), 185)
            self.assertEqual(sum(a['kind'] == 'assessment' for a in result['actions']), 63)
            self.assertEqual(sum(a['kind'] == 'training' for a in result['actions']), 122)
            self.assertEqual(len(result['images']), 656)
            self.assertEqual(len(set(a['id'] for a in result['actions'])), 185)
            self.assertFalse(result['measurement_bindings'])
            for action in result['actions']:
                self.assertTrue(action['name'])
                self.assertTrue(action['introduction'])
                self.assertTrue(action['source_content'])
                self.assertTrue(action['overview'])
                for slot in [action['overview'], *action['steps']]:
                    image = result['images'][slot]
                    self.assertEqual(image['action_id'], action['id'])
                    self.assertTrue((Path(folder)/Path(image['url']).name).is_file())
                    self.assertNotIn('phase', image)
                    self.assertNotIn('side', image)
            self.assertEqual(json.loads((Path(folder)/'catalogue.json').read_text(encoding='utf-8')), result)
            deadlift = next(a for a in result['actions'] if a['id'] == 'T-LOW-060')
            self.assertIn('硬拉', deadlift['name'])
            self.assertEqual(len(deadlift['steps']), 4)

    def test_intro_and_build_loaders_are_not_placeholders_or_internal_preview(self):
        capture = (ROOT/'mobile_rehab/static/rehab-v51-capture.js').read_text(encoding='utf-8')
        self.assertNotIn('专业介绍待完善', capture)
        for page in ('index.html', 'unified.html'):
            self.assertIn('/static/rehab-library.js', (ROOT/'mobile_rehab/static'/page).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
