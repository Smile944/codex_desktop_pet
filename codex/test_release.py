"""Release supply-chain and relocation checks."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import release
import build
from unittest.mock import patch


class ReleaseTests(unittest.TestCase):
    def archive(self, root, name='python/bin/python3', link=None):
        path = root / 'runtime.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            info = tarfile.TarInfo(name)
            if link:
                info.type = tarfile.SYMTYPE
                info.linkname = link
                archive.addfile(info)
            else:
                content = b'runtime'
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        return path

    def test_corrupt_runtime_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self.archive(root)
            with self.assertRaises(ValueError):
                release.extract_runtime(archive, root/'out', '0'*64)
            self.assertFalse((root/'out').exists())

    def test_archive_traversal_rejected(self):
        for name, link in [('../escape', None), ('python/bin/python3', '/tmp/escape'),
                           ('python/bin/python3', '../../../escape')]:
            with self.subTest(name=name, link=link), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                archive = self.archive(root, name, link)
                with self.assertRaises(ValueError):
                    release.extract_runtime(archive, root/'out', hashlib.sha256(archive.read_bytes()).hexdigest())
                self.assertFalse((root/'escape').exists())

    def test_valid_runtime_extracts_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self.archive(root)
            release.extract_runtime(archive, root/'out', hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual((root/'out/python/bin/python3').read_bytes(), b'runtime')

    def test_packaged_launcher_uses_relative_runtime(self):
        launcher = build.launcher_script(True)
        self.assertIn('../Resources/python/bin/python3', launcher)
        self.assertNotIn(__import__('sys').executable, launcher)
        self.assertIn('unset PYTHONHOME PYTHONPATH', launcher)

    def test_installer_signing_preserves_nested_media_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer=Path(tmp)/'installer.app'
            with patch.object(release,'run') as run:
                release.sign_installer(installer)
            signing=run.call_args_list[0].args
            self.assertNotIn('--deep',signing)
            self.assertIn('--deep',run.call_args_list[1].args)

    def test_runtime_locks_have_exact_versions_and_digests(self):
        locks = json.loads((Path(__file__).parent/'runtime-lock.json').read_text())
        self.assertEqual(set(locks), {'arm64','x86_64'})
        for lock in locks.values():
            self.assertRegex(lock['sha256'], '^[0-9a-f]{64}$')
            self.assertIn('/releases/download/20261026/', lock['url'])


if __name__ == '__main__':
    unittest.main()
