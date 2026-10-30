"""Preflight and source installation for the macOS Codex companion.

Only --check is read-only. Installation delegates to the existing installers,
which preserve user settings and replace/start the user-local companion app.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

# --check must not leave bytecode or other generated files in the source tree.
sys.dont_write_bytecode = True
from usage import CLI_CANDIDATES

ROOT = Path(__file__).resolve().parents[1]


def probe(args):
    """Run a bounded, read-only dependency query and return its text."""
    result = subprocess.run(args, check=True, capture_output=True, text=True, timeout=30)
    return result.stdout.strip()


def preflight(root):
    """Return all actionable dependency errors without modifying installation."""
    errors = []
    if sys.platform != 'darwin':
        return ['此安装器仅支持 macOS。']
    if sys.version_info < (3, 9):
        errors.append('需要 Python 3.9 或更新版本；请使用 Install.command 自动选择运行环境。')
    cli = next((p for p in CLI_CANDIDATES if Path(p).is_file() and os.access(p, os.X_OK)), None)
    if cli is None:
        errors.append('找不到 Codex CLI。请将 Codex.app 或包含 Codex CLI 的 ChatGPT.app 安装到 /Applications，然后重新运行。')
    else:
        try:
            probe([cli, '--version'])
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append('Codex CLI 无法运行：' + str(exc))
    try:
        compiler = probe(['/usr/bin/xcrun', '--find', 'swiftc'])
        sdk = probe(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-path'])
        if not compiler or not sdk:
            raise OSError('未找到 Swift 编译器或 macOS SDK')
        probe(['/usr/bin/swiftc', '--version'])
    except (OSError, subprocess.SubprocessError) as exc:
        errors.append('需要可用的 Apple Command Line Tools（含 Swift 和 macOS SDK），无需完整 Xcode。'
                      '请自行安装或修复后重试；可在终端运行 xcode-select --install。详情：' + str(exc))
    if not os.access('/usr/bin/codesign', os.X_OK):
        errors.append('找不到 macOS codesign 工具，无法签署本机应用。')
    required = ('codex/build.py', 'codex/install.py', 'codex/install_plugin.py',
                'codex/plugin', 'codex/ui', 'codex/vendor', 'assets', 'lib',
                'native/macos/Sources', 'native/macos/Info.plist', 'LICENSE', 'ASSET_LICENSE.md')
    missing = [name for name in required if not (root / name).exists()]
    if missing:
        errors.append('源码不完整，请下载并解压完整仓库：' + '、'.join(missing))
    return errors


def run_install(root):
    """Stop on the first failed stage; pin all stages to this usable runtime."""
    for name, label in (('build.py', '构建桌宠'), ('install.py', '安装并启动桌宠'),
                        ('install_plugin.py', '注册 Codex 插件'), ('install_hooks.py', '准备待审查的观察 Hooks')):
        print(label + '…', flush=True)
        subprocess.run([sys.executable, '-B', str(root / 'codex' / name)], cwd=str(root), check=True)


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description='从源码构建、安装桌宠并注册 codex-bigfish 插件。')
    parser.add_argument('--check', action='store_true', help='仅检查依赖，不构建、不安装、不重启应用')
    args = parser.parse_args(argv)
    print('Python：' + sys.executable, flush=True)
    errors = preflight(root)
    if errors:
        print('安装前检查未通过：\n' + '\n'.join(' - ' + error for error in errors))
        return 1
    print('依赖检查通过。', flush=True)
    if args.check:
        print('仅检查已完成；未执行构建或安装。')
        return 0
    try:
        run_install(root)
    except (OSError, subprocess.SubprocessError) as exc:
        print('安装中断：' + str(exc))
        print('已完成的步骤可能已生效。修复上方错误后可重新运行；用户设置不会被重置。')
        return 1
    print('桌宠及 codex-bigfish 插件已安装。请在 Codex 插件页确认插件已启用；如未出现，请重启 Codex。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
