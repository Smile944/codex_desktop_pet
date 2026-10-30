"""Installer safety and portability contracts; never installs the real app."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('bigfish_setup', HERE / 'setup.py')
setup = importlib.util.module_from_spec(SPEC)
if SPEC.origin and Path(SPEC.origin).exists():
    SPEC.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_check_does_not_run_install_scripts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(setup, 'preflight', return_value=[]), redirect_stdout(io.StringIO()):
                self.assertEqual(setup.main(['--check'], root=root), 0)
            self.assertEqual(list(root.iterdir()), [])

    def test_failed_preflight_blocks_all_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(setup, 'preflight', return_value=['缺少 Swift 编译器']), redirect_stdout(io.StringIO()):
                self.assertEqual(setup.main([], root=root), 1)
            self.assertEqual(list(root.iterdir()), [])

    def test_stages_share_python_and_run_in_order(self):
        with tempfile.TemporaryDirectory(prefix='bigfish setup ') as directory:
            root = Path(directory)
            (root / 'codex').mkdir()
            for name in ('build.py', 'install.py', 'install_plugin.py', 'install_hooks.py'):
                (root / 'codex' / name).write_text(
                    'import pathlib, sys\n'
                    'with pathlib.Path("trace").open("a") as output:\n'
                    '    output.write(pathlib.Path(__file__).name + "|" + sys.executable + "\\n")\n')
            setup.run_install(root)
            lines = (root / 'trace').read_text().splitlines()
            self.assertEqual(lines, [name + '|' + sys.executable for name in
                                    ('build.py', 'install.py', 'install_plugin.py', 'install_hooks.py')])

    def test_failure_stops_later_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'codex').mkdir()
            (root / 'codex/build.py').write_text('raise SystemExit(7)\n')
            (root / 'codex/install.py').write_text('raise RuntimeError("must never run")\n')
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                setup.run_install(root)
            self.assertEqual(caught.exception.returncode, 7)

    def test_preflight_requires_macos(self):
        with patch.object(setup.sys, 'platform', 'linux'):
            self.assertTrue(any('macOS' in error for error in setup.preflight(HERE.parent)))

    def test_preflight_accepts_clt_without_full_xcode(self):
        with tempfile.TemporaryDirectory() as directory:
            cli = Path(directory) / 'codex'
            cli.write_text('#!/bin/sh\nexit 0\n')
            cli.chmod(0o755)
            def probe(args, **kwargs):
                values = {
                    ('/usr/bin/xcrun', '--find', 'swiftc'): '/Library/Developer/CommandLineTools/usr/bin/swiftc\n',
                    ('/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-path'): '/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk\n',
                    ('/usr/bin/swiftc', '--version'): 'Apple Swift version\n',
                    (str(cli), '--version'): 'codex-cli\n',
                }
                return subprocess.CompletedProcess(args, 0, values.get(tuple(args), ''), '')
            with patch.object(setup.sys, 'platform', 'darwin'), patch.object(setup, 'CLI_CANDIDATES', (str(cli),)), patch.object(setup.subprocess, 'run', side_effect=probe):
                self.assertEqual(setup.preflight(HERE.parent), [])

    def test_missing_cli_and_compiler_are_actionable_errors(self):
        def failed(args, **kwargs):
            raise FileNotFoundError(str(args[0]))
        with patch.object(setup.sys, 'platform', 'darwin'), patch.object(setup, 'CLI_CANDIDATES', ()), patch.object(setup.subprocess, 'run', side_effect=failed):
            errors = setup.preflight(HERE.parent)
        self.assertTrue(any('Codex' in error for error in errors))
        self.assertTrue(any('Command Line Tools' in error for error in errors))


class LauncherTests(unittest.TestCase):
    def fixture(self, root):
        launcher = root / 'Install.command'
        launcher.write_bytes((HERE.parent / 'Install.command').read_bytes())
        launcher.chmod(0o755)
        (root / 'codex').mkdir()
        (root / 'codex/setup.py').write_text('import sys\nprint("fixture:" + "|".join(sys.argv[1:]))\n')
        return launcher

    def fake_python(self, path, label, usable=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/sh\nif [ "$1" = "-c" ]; then exit ' + ('0' if usable else '1') + '; fi\nprintf "' + label + '\\n"\nexec "' + sys.executable + '" "$@"\n')
        path.chmod(0o755)

    def test_bundled_runtime_preferred_and_arguments_preserved(self):
        with tempfile.TemporaryDirectory(prefix='bigfish launcher ') as directory:
            root = Path(directory)
            launcher = self.fixture(root)
            home = root / 'home'
            self.fake_python(home / '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3', 'bundled')
            self.fake_python(root / 'bin/python3', 'fallback')
            result = subprocess.run(['/bin/bash', str(launcher), '--check'], env={**os.environ, 'HOME': str(home), 'PATH': str(root / 'bin')}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('bundled\n', result.stdout)
            self.assertNotIn('fallback\n', result.stdout)
            self.assertIn('fixture:--check', result.stdout)

    def test_unusable_bundled_runtime_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = self.fixture(root)
            home = root / 'home'
            self.fake_python(home / '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3', 'broken', usable=False)
            self.fake_python(root / 'bin/python3', 'fallback')
            result = subprocess.run(['/bin/bash', str(launcher), '--check'], env={**os.environ, 'HOME': str(home), 'PATH': str(root / 'bin')}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('fallback\n', result.stdout)


if __name__ == '__main__':
    unittest.main()
