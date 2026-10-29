"""User-local install/uninstall; never modifies the Codex application."""
import argparse
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent / 'dist/大肥鱼 · Codex.app'
DEST = Path.home() / 'Applications/大肥鱼 · Codex.app'
LABEL = 'local.codex.bigfish'
PLIST = Path.home() / f'Library/LaunchAgents/{LABEL}.plist'
DATA = Path.home() / 'Library/Application Support/Codex BigFish'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args()
    domain = 'gui/' + str(os.getuid())
    subprocess.run(['/bin/launchctl', 'bootout', domain + '/' + LABEL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if args.uninstall:
        PLIST.unlink(missing_ok=True)
        if DEST.exists():
            shutil.rmtree(DEST)
        print('已移除应用和自动启动配置；用户设置保留于 ' + str(DATA))
        return
    if not SOURCE.is_dir():
        raise SystemExit('先运行 codex/build.py')
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(SOURCE, DEST)
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    resources = DEST / 'Contents/Resources'
    value = dict(Label=LABEL, ProgramArguments=[sys.executable, '-B', '-u', str(resources / 'codex/host.py'),
                 '--resources', str(resources), '--helper', str(resources / 'BigFish Helper.app/Contents/MacOS/bigfish-helper')],
                 RunAtLoad=True, KeepAlive=True, ThrottleInterval=15,
                 StandardOutPath=str(DATA / 'host.log'), StandardErrorPath=str(DATA / 'host.log'),
                 ProcessType='Background')
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(plistlib.dumps(value))
    PLIST.chmod(0o600)
    subprocess.run(['/bin/launchctl', 'bootstrap', domain, str(PLIST)], check=True)
    subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(DEST)], check=True)
    print(str(DEST))


if __name__ == '__main__':
    main()
