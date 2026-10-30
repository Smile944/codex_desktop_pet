"""Mount and relocate a DMG into a temporary user home; no live install changes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from install import install_app, installed_python
from install_plugin import prepare_package


def run(*args, **kwargs):
    try:
        return subprocess.run([str(a) for a in args], check=True, capture_output=True, text=True,
                              timeout=120, **kwargs)
    except subprocess.CalledProcessError as exc:
        print(exc.stdout or '', file=sys.stderr)
        print(exc.stderr or '', file=sys.stderr)
        raise


def verify(dmg, execute=True):
    with tempfile.TemporaryDirectory(prefix='bigfish release 中文 ') as tmp:
        root = Path(tmp)
        mount = root/'下载磁盘'
        mount.mkdir()
        home = root/'新 用户'
        app = home/'Applications/大肥鱼 · Codex.app'
        plist = home/'Library/LaunchAgents/local.codex.bigfish.plist'
        data = home/'Library/Application Support/Codex BigFish'
        attached = False
        try:
            run('/usr/bin/hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mount, dmg)
            attached = True
            installer = mount/'安装大肥鱼 · Codex.app'
            run('/usr/bin/codesign', '--verify', '--deep', '--strict', installer)
            payload = installer/'Contents/Resources/大肥鱼 · Codex.app'
            manifest = json.loads((payload/'Contents/Resources/release.json').read_text())
            helper = payload/'Contents/Resources/BigFish Helper.app/Contents/MacOS/bigfish-helper'
            binary = run('/usr/bin/file', helper).stdout
            assert manifest['arch'] in binary, binary
            if execute:
                run(installer/'Contents/MacOS/install', '--check')
            data.mkdir(parents=True)
            (data/'config.json').write_text('{"scale":0.37}')
            install_app(payload, app, plist, data, start=False)
        finally:
            if attached:
                run('/usr/bin/hdiutil', 'detach', mount)
        runtime = installed_python(app)
        config = plistlib.loads(plist.read_bytes())
        assert config['ProgramArguments'][0] == runtime
        assert not any(str(mount) in a for a in config['ProgramArguments'])
        assert (data/'config.json').read_text() == '{"scale":0.37}'
        run('/usr/bin/codesign', '--verify', '--deep', '--strict', app)
        package = data/'plugin-marketplace/plugins/codex-bigfish'
        prepare_package(app/'Contents/Resources/codex/plugin', package, runtime)
        if execute:
            env = dict(os.environ, HOME=str(home), CODEX_HOME=str(home/'.codex'), PATH='/usr/bin:/bin')
            env.pop('PYTHONHOME', None)
            env.pop('PYTHONPATH', None)
            imports = run(runtime, '-E', '-s', '-B', '-c',
                          'import ssl,sqlite3,ctypes,lzma,http.server,platform; print(platform.machine())', env=env)
            assert imports.stdout.strip() == manifest['arch']
            methods = [
                {'method':'initialize','params':{}},
                {'method':'tools/list','params':{}},
                {'method':'resources/read','params':{'uri':'ui://codex-bigfish/companion'}},
                {'method':'tools/call','params':{'name':'get_manifest','arguments':{}}},
            ]
            requests = '\n'.join(json.dumps(dict(jsonrpc='2.0', id=i+1, **v)) for i,v in enumerate(methods))+'\n'
            result = run('./run-server', cwd=package, env=env, input=requests)
            replies = [json.loads(line) for line in result.stdout.splitlines()]
            assert len(replies) == 4
            assert all('result' in reply for reply in replies), replies
            assert replies[0]['result']['serverInfo']['version'] == manifest['version']
            assert len(replies[1]['result']['tools']) == 9
            assert '启用大肥鱼' in replies[2]['result']['contents'][0]['text']
            assert len(replies[3]['result']['structuredContent']['clips']) == 16
            # Use the real CLI in a disposable HOME/CODEX_HOME, never the user's registry.
            (home/'.codex').mkdir()
            run(runtime, '-E', '-s', '-B', app/'Contents/Resources/codex/install_plugin.py', env=env)
            run(runtime, '-E', '-s', '-B', app/'Contents/Resources/codex/install_hooks.py', env=env)
            verification = str(Path(__file__).resolve().parent)
            native = run(runtime, '-E', '-s', '-B', '-c',
                         'import sys,json; sys.path.insert(0,'+repr(verification)+'); '
                         'from verify_mcp_plugin import native_discovery; '
                         'print(json.dumps(native_discovery('+repr(manifest['version'])+',include_hooks=True)))', env=env)
            discovery = json.loads(native.stdout)
            assert discovery['settingsCapability'] and discovery['discoveredToolCount'] == 9
        return dict(arch=manifest['arch'], version=manifest['version'], runtimeExecuted=execute,
                    mountedAndDetached=True, relocatedSignature=True, independentOfDownload=True,
                    sandboxNativeDiscovery=discovery if execute else None,
                    sha256=hashlib.sha256(dmg.read_bytes()).hexdigest(), bytes=dmg.stat().st_size)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('dmg', type=Path)
    parser.add_argument('--static-only', action='store_true', help='Do not execute foreign architecture binaries')
    args = parser.parse_args()
    print(json.dumps(verify(args.dmg.resolve(), not args.static_only), ensure_ascii=False, indent=2))
