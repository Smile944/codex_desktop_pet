import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import pet_packs as packs


class PetPackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.builtin = self.root/'assets'
        self.builtin.mkdir()
        (self.builtin/'pet-manifest.json').write_text(json.dumps({'clips': {'idle': {'frames': ['idle/a.webp']}}, 'name':'原版'}))
        self.store = packs.PackStore(self.builtin, self.root/'data')

    def source(self):
        config = self.root/'cat-config.json'
        config.write_text(json.dumps({'pets':[{'name':'猫咪'}], 'animations':{'idle':['呼吸'], 'clicks':['挥手']}, 'animationWeights':{'idle':10}}))
        media = self.root/'cat-animation'
        media.mkdir(exist_ok=True)
        (media/'呼吸.webm').write_bytes(b'fixture')
        (media/'挥手.webm').write_bytes(b'fixture')
        return config

    @staticmethod
    def encode(source, target, ffmpeg):
        target.mkdir(parents=True)
        (target/'frame_00001.webp').write_bytes(b'fixture-webp')
        return [target/'frame_00001.webp']

    def test_jsonc_does_not_strip_urls_or_quotes(self):
        self.assertEqual(packs.read_jsonc('{/* hi */"url":"https://a//b", "q":"\\\"//", //end\n"x":[1,],}'),
                         {'url':'https://a//b','q':'"//','x':[1]})

    def test_import_upstream_owns_assets_and_can_resolve(self):
        config = self.source()
        with patch.object(packs, 'encode_video', side_effect=self.encode):
            value = self.store.import_pack(config)
        self.assertEqual(value['name'], '猫咪')
        self.assertEqual(value['clipCount'],2)
        self.assertEqual(len(self.store.list()),2)
        manifest = json.loads((self.store.resolve(value['id'])/'pet-manifest.json').read_text())
        self.assertEqual(manifest['stateMap']['WORKING'], '呼吸')
        self.assertEqual(manifest['animations']['clicks'], ['挥手'])
        self.assertEqual(manifest['clips']['呼吸']['frames'][0].split('/')[0], packs.clip_key('呼吸'))
        self.assertNotIn('poke',manifest['clips'])

    def test_event_bands_accept_candidate_pools(self):
        config={'animations':{'idle':['呼吸'], 'events':{'balance':[['富有','平常'],'告急']}}}
        _,_,names=packs.normalize_config(config)
        self.assertEqual(names,{'呼吸','富有','平常','告急'})
        config['animations']['events']['balance']=[[]]
        with self.assertRaises(ValueError):packs.normalize_config(config)

    def test_infinite_motion_is_rejected(self):
        config={'animations':{'idle':['呼吸'],'moves':{'default':{'leadSec':float('inf')}}}}
        with self.assertRaises(ValueError):packs.normalize_config(config)

    def test_missing_media_rolls_back_without_borrowing_builtin(self):
        config = self.source()
        (self.root/'cat-animation/挥手.webm').unlink()
        with self.assertRaises(ValueError):
            self.store.import_pack(config)
        self.assertEqual([p['id'] for p in self.store.list()],['builtin'])

    def test_failed_conversion_rolls_back(self):
        config = self.source()
        with patch.object(packs,'encode_video',side_effect=ValueError('invalid media')):
            with self.assertRaises(ValueError):self.store.import_pack(config)
        self.assertEqual([p['id'] for p in self.store.list()],['builtin'])
        self.assertEqual(list((self.root/'data/packs').glob('.import-*')),[])

    def test_source_symlink_is_rejected(self):
        config = self.source()
        media = self.root/'cat-animation/呼吸.webm'
        media.unlink();media.symlink_to(self.builtin/'pet-manifest.json')
        with self.assertRaises(ValueError):self.store.import_pack(config)

    def test_traversal_name_and_nonfinite_weight_rejected(self):
        for animations in ({'idle':['../escape']},{'idle':['/tmp/a']},{'idle':[]}):
            with self.assertRaises(ValueError):packs.normalize_config({'animations':animations})
        with self.assertRaises(ValueError):packs.normalize_config({'animations':{'idle':['a']},'animationWeights':{'idle':float('nan')}})

    def test_resolve_rejects_path_and_symlink_escape(self):
        for name in ('../a','/tmp','',True):
            with self.assertRaises(ValueError):self.store.resolve(name)
        location = self.root/'data/packs/escape';location.parent.mkdir(parents=True,exist_ok=True)
        location.symlink_to(self.builtin)
        with self.assertRaises(ValueError):self.store.resolve('escape')

    def test_zip_traversal_and_symlink_rejected(self):
        for symlink in (False,True):
            path = self.root/'pack.zip'
            with zipfile.ZipFile(path,'w') as archive:
                if symlink:
                    info = zipfile.ZipInfo('a');info.external_attr=(0o120777<<16)
                    archive.writestr(info,'outside')
                else:archive.writestr('../outside','evil')
            with self.assertRaises(ValueError):self.store.import_pack(path)
            self.assertFalse((self.root/'outside').exists())

    def test_zip_nested_pack_import(self):
        self.source()
        archive = self.root/'cat.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for p in (self.root/'cat-config.json',self.root/'cat-animation/呼吸.webm',self.root/'cat-animation/挥手.webm'):
                z.write(p,Path('download/pet')/p.relative_to(self.root))
        with patch.object(packs,'encode_video',side_effect=self.encode):
            result = self.store.import_pack(archive)
        self.assertEqual(result['name'],'猫咪')


if __name__=='__main__':unittest.main()
