"""User-local install/uninstall; never modifies the Codex application."""
import argparse
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parent / 'dist/大肥鱼 · Codex.app'
DEST = Path.home() / 'Applications/大肥鱼 · Codex.app'
LABEL = 'local.codex.bigfish'
PLIST = Path.home() / f'Library/LaunchAgents/{LABEL}.plist'
DATA = Path.home() / 'Library/Application Support/Codex BigFish'


def installed_python(app):
    """A packaged app always uses its own runtime after relocation."""
    embedded = app / 'Contents/Resources/python/bin/python3'
    return str(embedded) if embedded.is_file() else sys.executable


def install_app(source, dest=DEST, plist=PLIST, data=DATA, start=True):
    if not source.is_dir():
        raise OSError('找不到完整应用：' + str(source))
    dest.parent.mkdir(parents=True, exist_ok=True)
    domain = 'gui/' + str(os.getuid())
    # Finish the potentially expensive copy before stopping a working app.
    with tempfile.TemporaryDirectory(prefix='.bigfish-install-', dir=dest.parent) as tmp:
        stage = Path(tmp) / dest.name
        backup = Path(tmp) / 'previous.app'
        shutil.copytree(source, stage, symlinks=True)
        previous_plist = plist.read_bytes() if plist.exists() else None
        stopped = False
        replaced = False
        try:
            if start:
                subprocess.run(['/bin/launchctl', 'bootout', domain + '/' + LABEL],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                stopped = True
            if dest.exists():
                dest.rename(backup)
            stage.rename(dest)
            replaced = True
            data.mkdir(parents=True, exist_ok=True, mode=0o700)
            resources = dest / 'Contents/Resources'
            value = dict(Label=LABEL, ProgramArguments=[installed_python(dest), '-E', '-s', '-B', '-u',
                         str(resources / 'codex/host.py'), '--resources', str(resources),
                         '--helper', str(resources / 'BigFish Helper.app/Contents/MacOS/bigfish-helper')],
                         RunAtLoad=True, KeepAlive=True, ThrottleInterval=15,
                         StandardOutPath=str(data / 'host.log'), StandardErrorPath=str(data / 'host.log'),
                         ProcessType='Background')
            plist.parent.mkdir(parents=True, exist_ok=True)
            temporary = plist.with_suffix('.tmp')
            temporary.write_bytes(plistlib.dumps(value))
            temporary.chmod(0o600)
            temporary.replace(plist)
            if start:
                subprocess.run(['/bin/launchctl', 'bootstrap', domain, str(plist)], check=True)
        except Exception:
            if replaced and dest.exists():
                shutil.rmtree(dest)
            if backup.exists():
                backup.rename(dest)
            if previous_plist is None:
                plist.unlink(missing_ok=True)
            else:
                plist.write_bytes(previous_plist)
                plist.chmod(0o600)
                if stopped:
                    subprocess.run(['/bin/launchctl', 'bootstrap', domain, str(plist)], check=False)
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args()
    domain = 'gui/' + str(os.getuid())
    if args.uninstall:
        subprocess.run(['/bin/launchctl', 'bootout', domain + '/' + LABEL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        PLIST.unlink(missing_ok=True)
        if DEST.exists():
            shutil.rmtree(DEST)
        print('已移除应用和自动启动配置；用户设置保留于 ' + str(DATA))
        return
    if not SOURCE.is_dir():
        raise SystemExit('先运行 codex/build.py')
    subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(SOURCE)], check=True)
    install_app(SOURCE)
    print(str(DEST))


if __name__ == '__main__':
    main()
