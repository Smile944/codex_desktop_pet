import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


def policy():
    spec=importlib.util.spec_from_file_location('animation_policy',ROOT/'scripts/animation_policy.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class AnimationPolicyTests(unittest.TestCase):
    def test_shipped_actions_do_not_contain_removed_term(self):
        manifest=json.loads((ROOT/'assets/pet-manifest.json').read_text())
        blocked=[key for key,clip in manifest['clips'].items() if '女仆' in key or '女仆' in manifest['clipLabels'].get(key,'') or '女仆' in clip.get('source',{}).get('file','')]
        self.assertEqual(blocked,[])
        self.assertEqual(len(manifest['libraryClips']),104)
        self.assertEqual(sum(len(manifest['clips'][key]['frames']) for key in manifest['libraryClips']),24941)
        self.assertNotIn('女仆',json.dumps(manifest['animations'],ensure_ascii=False))

    def test_policy_preserves_weights_and_other_actions_without_mutating_source(self):
        source={'animations':{'idle':['呼吸'],'categories':[{'id':'玩耍','weight':20,'actions':['优雅女仆舞','跳舞']}]},'animationWeights':{'idle':10}}
        result=policy().filter_config(source)
        self.assertEqual(result['animations']['categories'][0]['actions'],['跳舞'])
        self.assertEqual(result['animations']['categories'][0]['weight'],20)
        self.assertEqual(source['animations']['categories'][0]['actions'],['优雅女仆舞','跳舞'])

    def test_manifest_removes_aliases_and_all_playback_references(self):
        manifest={'clips':{'idle':{'frames':['idle/a.webp']},'maid_alias':{'frames':['bad/a.webp'],'source':{'file':'女仆屈膝礼仪.webm'}}},
                  'clipLabels':{'maid_alias':'女仆屈膝礼仪'},'libraryClips':['idle','maid_alias'],
                  'stateMap':{'IDLE':'idle','WORKING':'maid_alias'},'workingActivityMap':{'editing':'maid_alias'},
                  'idleMicroClips':['maid_alias','idle'],'animations':{'idle':['idle'],'categories':[{'id':'x','weight':20,'actions':['maid_alias','idle']}]}}
        result,removed=policy().filter_manifest(manifest)
        self.assertEqual(removed,{'maid_alias'})
        self.assertEqual(set(result['clips']),{'idle'})
        self.assertEqual(result['stateMap']['WORKING'],'idle')
        self.assertEqual(result['animations']['categories'][0]['actions'],['idle'])
        self.assertEqual(result['idleMicroClips'],['idle'])


if __name__=='__main__':unittest.main()
