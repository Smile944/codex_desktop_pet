import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('verify_release',ROOT/'codex/verification/verify_release.py')
verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)


class ReleaseVerifierTests(unittest.TestCase):
    def test_canonical_manifest_counts_ignore_compatibility_aliases(self):
        manifest=json.loads((ROOT/'assets/pet-manifest.json').read_text())
        self.assertEqual(verifier.verify_library(manifest),{'canonicalClips':106,'canonicalFrames':25423})
        manifest['libraryClips']=manifest['libraryClips'][:-1]
        with self.assertRaises(AssertionError):verifier.verify_library(manifest)

    def test_offline_host_serves_selected_pack_without_helper_or_real_user_data(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)/'home';home.mkdir()
            data=home/'Library/Application Support/Codex BigFish'
            env=verifier.sandbox_environment(home,data)
            with verifier.local_host(sys.executable,ROOT,data,env) as process:
                import urllib.request
                endpoint=json.loads((data/'endpoint.json').read_text())
                with urllib.request.urlopen(endpoint['url']+'/plugins/dsh-dafeiyu/packs',timeout=3) as reply:
                    packs=json.load(reply)
                self.assertEqual(packs['selected'],'builtin')
                self.assertEqual(len(packs['manifest']['libraryClips']),106)
                with urllib.request.urlopen(endpoint['url']+'/health',timeout=3) as reply:
                    health=json.load(reply)
                self.assertFalse(health['helperRunning'])
                self.assertIsNone(process.poll())
            self.assertIsNotNone(process.poll())
            self.assertEqual(env['HOME'],str(home))
            self.assertEqual(env['CODEX_BIGFISH_HOME'],str(data))


if __name__=='__main__':unittest.main()
