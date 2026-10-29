"""Standalone installation must survive removal of its download directory."""
import importlib
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import install as desktop_install
import install_plugin


class PortableInstallTests(unittest.TestCase):
    def fixture(self, root):
        app = root / '下载 磁盘/大肥鱼 · Codex.app'
        resources = app / 'Contents/Resources'
        runtime = resources / 'python/bin/python3'
        runtime.parent.mkdir(parents=True)
        runtime.write_text('#!/bin/sh\nexec ' + __import__('shlex').quote(sys.executable) + ' "$@"\n')
        runtime.chmod(0o755)
        (resources / 'codex').mkdir()
        (resources / 'codex/host.py').write_text('')
        (resources / 'BigFish Helper.app/Contents/MacOS').mkdir(parents=True)
        shutil.copytree(Path(__file__).parent / 'plugin', resources / 'codex/plugin')
        return app

    def test_installed_paths_use_embedded_python_and_preserve_settings(self):
        with tempfile.TemporaryDirectory(prefix='bigfish 安装 ') as tmp:
            root = Path(tmp)
            source = self.fixture(root)
            dest = root / '新用户/Applications/大肥鱼 · Codex.app'
            plist = root / '新用户/Library/LaunchAgents/local.codex.bigfish.plist'
            data = root / '新用户/Library/Application Support/Codex BigFish'
            data.mkdir(parents=True)
            (data / 'config.json').write_text('{"scale":0.37}')
            desktop_install.install_app(source, dest, plist, data, start=False)
            runtime = dest / 'Contents/Resources/python/bin/python3'
            args = plistlib.loads(plist.read_bytes())['ProgramArguments']
            self.assertEqual(args[0], str(runtime))
            self.assertTrue(all(str(source) not in arg for arg in args))
            self.assertEqual((data / 'config.json').read_text(), '{"scale":0.37}')
            package = data / 'plugin-marketplace/plugins/codex-bigfish'
            install_plugin.prepare_package(dest / 'Contents/Resources/codex/plugin', package, str(runtime))
            shutil.rmtree(source.parent)
            request = json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})+'\n'
            process = subprocess.run(['./run-server'], cwd=package, input=request, text=True,
                                     capture_output=True, timeout=10, check=True)
            self.assertIn('openai/settings', json.loads(process.stdout)['result']['capabilities']['experimental'])

    def test_missing_source_does_not_remove_working_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / 'installed.app'
            dest.mkdir()
            (dest / 'keep').write_text('old version')
            with self.assertRaises(OSError):
                desktop_install.install_app(root/'missing.app', dest, root/'agent.plist', root/'data', start=False)
            self.assertEqual((dest/'keep').read_text(), 'old version')

    def test_copy_failure_leaves_old_installation_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.fixture(root)
            dest = root / 'installed.app'
            dest.mkdir()
            (dest / 'keep').write_text('old version')
            with patch.object(desktop_install.shutil, 'copytree', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    desktop_install.install_app(source, dest, root/'agent.plist', root/'data', start=False)
            self.assertEqual((dest/'keep').read_text(), 'old version')

    def test_check_reports_missing_host_without_install_or_compiler_probe(self):
        portable = importlib.import_module('portable_install')
        with tempfile.TemporaryDirectory() as tmp:
            source = self.fixture(Path(tmp))
            calls = []
            def run(args, **kwargs):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, '', '')
            with patch.object(portable, 'CLI_CANDIDATES', ()), patch.object(portable.subprocess, 'run', side_effect=run):
                errors = portable.preflight(source)
            self.assertTrue(any('Codex' in error for error in errors))
            self.assertFalse(any('swift' in str(call) or 'xcrun' in str(call) or 'launchctl' in str(call) for call in calls))

    def test_bootstrap_failure_restores_previous_application_and_plist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.fixture(root)
            dest = root / 'installed.app'
            dest.mkdir()
            (dest/'keep').write_text('old version')
            plist = root/'agent.plist'
            original = plistlib.dumps({'Label':'old'})
            plist.write_bytes(original)
            attempts = []
            def run(args, **kwargs):
                if 'bootstrap' in args:
                    attempts.append(args)
                    if len(attempts) == 1:
                        raise subprocess.CalledProcessError(5, args)
                return subprocess.CompletedProcess(args, 0)
            with patch.object(desktop_install.subprocess, 'run', side_effect=run):
                with self.assertRaises(subprocess.CalledProcessError):
                    desktop_install.install_app(source, dest, plist, root/'data')
            self.assertEqual((dest/'keep').read_text(), 'old version')
            self.assertEqual(plist.read_bytes(), original)
            self.assertEqual(len(attempts), 2)


if __name__ == '__main__':
    unittest.main()
