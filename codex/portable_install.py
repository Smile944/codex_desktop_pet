"""Install a prebuilt app. No compiler, system Python, or downloads required."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

sys.dont_write_bytecode = True
from install import DEST, PLIST, DATA, LABEL, install_app, installed_python
from usage import CLI_CANDIDATES


def preflight(source):
    errors = []
    if sys.platform != 'darwin':
        return ['此安装包仅支持 macOS。']
    if not any(Path(p).is_file() and os.access(p, os.X_OK) for p in CLI_CANDIDATES):
        errors.append('请先将 Codex.app 或包含 Codex CLI 的 ChatGPT.app 安装到 /Applications。')
    resources = source / 'Contents/Resources'
    try:
        manifest = json.loads((resources / 'release.json').read_text())
        if manifest['arch'] != platform.machine():
            errors.append('安装包架构不匹配，请下载本机芯片对应的 arm64 或 x86_64 安装包。')
        version = platform.mac_ver()[0].split('.')
        if int(version[0]) < 13:
            errors.append('此安装包要求 macOS 13 或更新版本。')
    except (OSError, ValueError, KeyError, IndexError):
        errors.append('安装包缺少有效的版本信息，请重新下载完整 DMG。')
    for name in ('python/bin/python3', 'codex/host.py', 'codex/plugin/server.py',
                 'BigFish Helper.app/Contents/MacOS/bigfish-helper'):
        if not (resources / name).is_file():
            errors.append('安装包不完整：' + name)
    try:
        subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(source)],
                       check=True, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        errors.append('安装包签名校验失败，请重新下载。')
    try:
        subprocess.run([str(resources / 'python/bin/python3'), '-E', '-s', '-B', '-c',
                        'import ssl, sqlite3, ctypes, lzma, http.server'],
                       check=True, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        errors.append('内置运行环境无法启动，请确认芯片版本并重新下载。')
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description='安装自带运行环境的大肥鱼桌宠')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args(argv)
    source = Path(__file__).resolve().parents[3]
    if args.uninstall:
        import install
        sys.argv = [sys.argv[0], '--uninstall']
        install.main()
        return 0
    errors = preflight(source)
    if errors:
        print('\n'.join(errors), flush=True)
        return 1
    if args.check:
        print('安装包、芯片架构、签名及 Codex 检查通过；未更改安装。', flush=True)
        return 0
    try:
        print('正在复制桌宠和内置运行环境…', flush=True)
        install_app(source)
        resources = DEST / 'Contents/Resources'
        print('正在注册 Codex 插件…', flush=True)
        subprocess.run([installed_python(DEST), '-E', '-s', '-B',
                        str(resources / 'codex/install_plugin.py')], check=True)
        subprocess.run([installed_python(DEST), '-E', '-s', '-B',
                        str(resources / 'codex/install_hooks.py')], check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        print('安装未完成：' + str(exc) + '\n请修复上方错误后重新运行安装器；用户设置保留。', flush=True)
        return 1
    print('安装完成。请在 Codex 设置 → 插件中打开大肥鱼；列表未刷新时重新进入或重启 Codex。', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
