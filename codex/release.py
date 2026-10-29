"""Build self-contained, architecture-specific DMGs. Build host needs CLT only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'codex/dist'


def extract_runtime(archive, output, digest):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise ValueError('Python archive SHA256 mismatch')
    with tarfile.open(archive, 'r:gz') as tar:
        base = output.resolve()
        for member in tar.getmembers():
            target = (base / member.name).resolve()
            if not target.is_relative_to(base) or not member.name.startswith('python/'):
                raise ValueError('Unsafe runtime archive path')
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                raise ValueError('Unsupported archive member')
            if member.issym() or member.islnk():
                linked = ((target.parent if member.issym() else base) / member.linkname).resolve()
                if not linked.is_relative_to(base):
                    raise ValueError('Unsafe runtime archive link')
        output.mkdir(parents=True, exist_ok=True)
        if hasattr(tarfile, 'data_filter'):
            tar.extractall(output, filter='data')
        else:
            tar.extractall(output)


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def build_release(arch):
    notices = ROOT/'codex/runtime-licenses'
    provenance = json.loads((notices/'PROVENANCE.json').read_text())
    for name, digest in provenance['files'].items():
        if hashlib.sha256((notices/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Runtime license inventory mismatch: '+name)
    lock = json.loads((ROOT/'codex/runtime-lock.json').read_text())[arch]
    cache = DIST / 'runtime-cache'
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / urllib.parse.unquote(lock['url'].rsplit('/', 1)[-1])
    if not archive.exists():
        temporary = archive.with_suffix('.download')
        urllib.request.urlretrieve(lock['url'], temporary)
        temporary.replace(archive)
    work = DIST / ('release-' + arch)
    if work.exists():
        shutil.rmtree(work)
    extract_runtime(archive, work/'runtime', lock['sha256'])
    version = json.loads((ROOT/'codex/plugin/plugin.json').read_text())['version']
    volume = work / 'volume'
    installer = volume / '安装大肥鱼 · Codex.app'
    contents = installer / 'Contents'
    resources = contents / 'Resources'
    resources.mkdir(parents=True)
    payload = resources / '大肥鱼 · Codex.app'
    run(sys.executable, '-B', ROOT/'codex/build.py', '--output', payload,
        '--python-runtime', work/'runtime/python', '--arch', arch)
    macos = contents / 'MacOS'
    macos.mkdir()
    run('/usr/bin/swiftc', '-O', '-swift-version', '5', '-target', arch+'-apple-macosx13.0',
        ROOT/'codex/Installer.swift', '-framework', 'AppKit', '-o', macos/'install')
    (contents/'Info.plist').write_bytes(plistlib.dumps(dict(
        CFBundleIdentifier='local.codex.bigfish.installer', CFBundleName='安装大肥鱼 · Codex',
        CFBundleDisplayName='安装大肥鱼 · Codex', CFBundleExecutable='install', CFBundlePackageType='APPL',
        CFBundleVersion=version, CFBundleShortVersionString=version, LSMinimumSystemVersion='13.0',
        NSHighResolutionCapable=True)))
    run('/usr/bin/codesign', '--force', '--deep', '--sign', '-', '--timestamp=none', installer)
    run('/usr/bin/codesign', '--verify', '--deep', '--strict', installer)
    shutil.copy2(ROOT/'codex/INSTALL-RELEASE.txt', volume/'安装说明.txt')
    shutil.copy2(ROOT/'LICENSE', volume/'LICENSE.txt')
    uninstall = volume/'卸载桌宠.command'
    uninstall.write_text('#!/bin/sh\nunset PYTHONHOME PYTHONPATH\napp="$HOME/Applications/大肥鱼 · Codex.app"\n'
                         '"$app/Contents/Resources/python/bin/python3" -E -s -B '
                         '"$app/Contents/Resources/codex/portable_install.py" --uninstall\n'
                         'printf "\\n请另在 Codex 插件页卸载大肥鱼。按回车关闭。"\nread -r answer\n')
    uninstall.chmod(0o755)
    releases = DIST/'releases'
    releases.mkdir(exist_ok=True)
    dmg = releases/f'Codex-BigFish-{version}-macOS-{arch}.dmg'
    run('/usr/bin/hdiutil', 'create', '-ov', '-format', 'UDZO', '-volname', 'Codex BigFish '+version,
        '-srcfolder', volume, dmg)
    run('/usr/bin/hdiutil', 'verify', dmg)
    print(json.dumps(dict(dmg=str(dmg), sha256=hashlib.sha256(dmg.read_bytes()).hexdigest()), ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--arch', choices=('arm64', 'x86_64'), required=True)
    build_release(parser.parse_args().arch)
