import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class MediaRuntimeTests(unittest.TestCase):
    def test_pkg_config_runs_with_a_spaced_interpreter_path(self):
        import build_media
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            interpreter = root / "大肥鱼 · Codex's.app/python3"
            interpreter.parent.mkdir()
            interpreter.symlink_to(sys.executable)
            adapter = root / 'media-pkg-config'
            build_media.write_pkg_config(adapter, Path('/tmp/media-prefix'), interpreter)
            result = subprocess.run([str(adapter), '--modversion', 'vpx'], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), '1.14.1')
            result = subprocess.run([str(adapter), '--libs', 'libwebp'], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), '-L/tmp/media-prefix/lib -lwebp -lsharpyuv -lm')

    def test_missing_runtime_fails_without_searching_path(self):
        import media_runtime as media
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                media.resolve_ffmpeg(Path(folder))

    def test_bundled_runtime_checks_digest_before_execution(self):
        import media_runtime as media
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / 'media/ffmpeg'
            target.parent.mkdir()
            target.write_bytes(b'fixture')
            target.chmod(0o755)
            lock = {'binaries': {'arm64': {'sha256': hashlib.sha256(b'fixture').hexdigest()}}}
            with patch.object(media, 'load_lock', return_value=lock), patch.object(media.platform, 'machine', return_value='arm64'):
                self.assertEqual(media.resolve_ffmpeg(root), target)
                target.write_bytes(b'corrupt')
                with self.assertRaises(ValueError): media.resolve_ffmpeg(root)

    def test_explicit_converter_must_be_executable(self):
        import media_runtime as media
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'ffmpeg'
            binary.write_bytes(b'local')
            binary.chmod(0o644)
            with self.assertRaises(ValueError): media.resolve_ffmpeg(explicit=binary)
            binary.chmod(0o755)
            self.assertTrue(media.resolve_ffmpeg(explicit=binary).samefile(binary))

    def test_corrupt_cached_source_is_rejected(self):
        import media_runtime as media
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.tar.gz'
            source.write_bytes(b'corrupt')
            with self.assertRaises(ValueError):
                media.verify_file(source, hashlib.sha256(b'correct').hexdigest())


if __name__ == '__main__': unittest.main()
