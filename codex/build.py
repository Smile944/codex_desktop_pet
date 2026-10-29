"""Build the original Helper with Codex host copy and user-selected scale policy."""
import hashlib
import argparse
import json
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from scale_policy import adapt_native_scale

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'codex/dist/大肥鱼 · Codex.app'


def run(*args):
    subprocess.run(args, check=True)


def launcher_script(embedded=False):
    python = '"$(dirname "$0")/../Resources/python/bin/python3"' if embedded else shlex.quote(sys.executable)
    return ('#!/bin/sh\nunset PYTHONHOME PYTHONPATH\nexec ' + python +
            ' -E -s -B "$(dirname "$0")/../Resources/codex/launcher.py"\n')


def build(app=APP, runtime=None, arch=None):
    contents = app / 'Contents'
    if app.exists():
        shutil.rmtree(app)
    resources = contents / 'Resources'
    macos = contents / 'MacOS'
    macos.mkdir(parents=True)
    resources.mkdir()
    for name in ('assets', 'lib'):
        shutil.copytree(ROOT / name, resources / name)
    for name in ('LICENSE', 'ASSET_LICENSE.md'):
        shutil.copy2(ROOT / name, resources / name)
    code = resources / 'codex'
    code.mkdir()
    for name in ('host.py', 'adapter.py', 'launcher.py', 'usage.py', 'scale_policy.py', 'client_bundle.py', 'runtime_status.py',
                 'install.py', 'install_plugin.py', 'portable_install.py'):
        shutil.copy2(ROOT / 'codex' / name, code / name)
    for name in ('ui', 'vendor', 'plugin'):
        shutil.copytree(ROOT / 'codex' / name, code / name)
    version = json.loads((ROOT / 'codex/plugin/plugin.json').read_text())['version']
    if runtime:
        shutil.copytree(runtime, resources / 'python', symlinks=True)
        shutil.copytree(ROOT / 'codex/runtime-licenses', resources / 'runtime-licenses')
        lock = json.loads((ROOT / 'codex/runtime-lock.json').read_text())[arch]
        (resources / 'release.json').write_text(json.dumps(dict(version=version, arch=arch, runtime=lock), indent=2)+'\n')
    helper = resources / 'BigFish Helper.app/Contents'
    helper_bin = helper / 'MacOS/bigfish-helper'
    helper_bin.parent.mkdir(parents=True)
    info = plistlib.loads((ROOT / 'native/macos/Info.plist').read_bytes())
    info.update(CFBundleIdentifier='local.codex.bigfish.helper', CFBundleExecutable='bigfish-helper',
                CFBundleName='大肥鱼 · Codex', CFBundleDisplayName='大肥鱼 · Codex',
                CFBundleVersion=version, CFBundleShortVersionString=version, LSMinimumSystemVersion='13.0')
    (helper / 'Info.plist').write_bytes(plistlib.dumps(info))
    # Preserve upstream files; adapt host labels and the user-requested scale range.
    generated = ROOT / 'codex/dist/native'
    generated.mkdir(parents=True, exist_ok=True)
    sources = []
    for source in sorted((ROOT / 'native/macos/Sources').glob('*.swift')):
        text = adapt_native_scale(source.read_text())
        for old, new in [('DSH 大肥鱼', 'Codex 大肥鱼'), ('DSH · 等待下一次任务', 'Codex · 等待下一次任务'),
                         ('DSH 任务', 'Codex 任务'), ('DSH 申请权限', 'Codex 申请权限'),
                         ('无法打开 DSH', '无法打开 Codex'), ('请确认 DSH 已安装', '请确认 Codex 已安装')]:
            text = text.replace(old, new)
        target = generated / source.name
        target.write_text(text)
        sources.append(str(target))
    target = ['-target', arch+'-apple-macosx13.0'] if arch else []
    run('/usr/bin/swiftc', '-O', '-swift-version', '5', *target, *sources,
        '-framework', 'AppKit', '-framework', 'UserNotifications',
        '-framework', 'ApplicationServices', '-framework', 'QuartzCore', '-o', str(helper_bin))
    run('/usr/bin/codesign', '--force', '--deep', '--sign', '-', '--timestamp=none', str(helper.parent))
    launcher = macos / 'launch'
    launcher.write_text(launcher_script(bool(runtime)))
    launcher.chmod(0o755)
    info.update(CFBundleIdentifier='local.codex.bigfish', CFBundleExecutable='launch')
    (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
    digests = {}
    for path in sorted((ROOT / 'assets').rglob('*')):
        if path.is_file():
            rel = path.relative_to(ROOT)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == hashlib.sha256((resources / rel).read_bytes()).hexdigest()
            digests[str(rel)] = digest
    (resources / 'upstream-assets.sha256.json').write_text(json.dumps(digests, indent=2))
    if runtime:
        # Sign every extension/library before sealing the enclosing bundle.
        for path in sorted((resources / 'python').rglob('*')):
            if path.is_symlink() or not path.is_file():
                continue
            with path.open('rb') as stream:
                magic = stream.read(4)
            if magic in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe'):
                run('/usr/bin/codesign', '--force', '--sign', '-', '--timestamp=none', str(path))
    run('/usr/bin/codesign', '--force', '--deep', '--sign', '-', '--timestamp=none', str(app))
    run('/usr/bin/codesign', '--verify', '--deep', '--strict', str(app))
    print(json.dumps(dict(app=str(app), identicalAssets=len(digests), embeddedRuntime=bool(runtime)), ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=APP)
    parser.add_argument('--python-runtime', type=Path)
    parser.add_argument('--arch', choices=('arm64', 'x86_64'))
    args = parser.parse_args()
    if args.python_runtime and not args.arch:
        parser.error('--python-runtime requires --arch')
    build(args.output, args.python_runtime, args.arch)
