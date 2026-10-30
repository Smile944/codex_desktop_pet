"""Mount and relocate a DMG into a temporary user home; no live install changes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from install import install_app, installed_python
from install_plugin import prepare_package


def run(*args, **kwargs):
    command = [str(arg) for arg in args]
    input_text = kwargs.pop('input', None)
    process = subprocess.Popen(command, stdin=subprocess.PIPE if input_text is not None else None,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               start_new_session=True, **kwargs)
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=120)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=10)
        print(stdout or '', file=sys.stderr)
        print(stderr or '', file=sys.stderr)
        raise
    if process.returncode:
        print(stdout or '', file=sys.stderr)
        print(stderr or '', file=sys.stderr)
        raise subprocess.CalledProcessError(process.returncode, command, stdout, stderr)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def sandbox_environment(home, data):
    env = dict(os.environ, HOME=str(home), CODEX_HOME=str(home/'.codex'),
               CODEX_BIGFISH_HOME=str(data), PATH='/usr/bin:/bin')
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    return env


def verify_library(manifest):
    canonical = manifest['libraryClips']
    assert len(canonical) == len(set(canonical)) == 106, 'canonical animation count'
    frames = sum(len(manifest['clips'][name]['frames']) for name in canonical)
    assert frames == 25423, f'canonical frame count: {frames}'
    return dict(canonicalClips=len(canonical), canonicalFrames=frames)


@contextmanager
def local_host(runtime, resources, data, env):
    """Serve only the bounded HTTP API; never run the host loop or native helper."""
    data.mkdir(parents=True, exist_ok=True)
    endpoint = data/'endpoint.json'
    endpoint.unlink(missing_ok=True)
    script = """
import json, signal, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1])/'codex'))
from host import Host
owner = Host(Path(sys.argv[1]), '/verification/no-native-helper')
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
try:
    (Path(sys.argv[2])/'endpoint.json').write_text(json.dumps({'url':owner.url,'pid':__import__('os').getpid()}))
    owner.server.serve_forever()
finally:
    owner.server.server_close()
"""
    process = subprocess.Popen([str(runtime), '-E', '-s', '-B', '-u', '-c', script, str(resources), str(data)],
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic()+20
        while not endpoint.exists():
            if process.poll() is not None:
                raise RuntimeError('Offline verification host exited before publishing its endpoint')
            if time.monotonic() > deadline:
                raise TimeoutError('Offline verification host startup timed out')
            time.sleep(0.05)
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=10)
        if stdout:
            print(stdout, file=sys.stderr)
        if stderr:
            print(stderr, file=sys.stderr)


def verify(dmg, execute=True):
    with tempfile.TemporaryDirectory(prefix='bigfish release 中文 ') as tmp:
        root = Path(tmp)
        mount = root/'下载磁盘'
        mount.mkdir()
        home = root/'新 用户'
        app = home/'Applications/大肥鱼 · Codex.app'
        plist = home/'Library/LaunchAgents/local.codex.bigfish.plist'
        data = home/'Library/Application Support/Codex BigFish'
        home.mkdir()
        env = sandbox_environment(home, data)
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
                run(installer/'Contents/MacOS/install', '--check', env=env)
            data.mkdir(parents=True)
            (data/'settings.json').write_text('{"scale":0.37}')
            install_app(payload, app, plist, data, start=False)
        finally:
            if attached:
                run('/usr/bin/hdiutil', 'detach', mount)
        runtime = installed_python(app)
        config = plistlib.loads(plist.read_bytes())
        assert config['ProgramArguments'][0] == runtime
        assert not any(str(mount) in a for a in config['ProgramArguments'])
        assert (data/'settings.json').read_text() == '{"scale":0.37}'
        run('/usr/bin/codesign', '--verify', '--deep', '--strict', app)
        package = data/'plugin-marketplace/plugins/codex-bigfish'
        prepare_package(app/'Contents/Resources/codex/plugin', package, runtime)
        if execute:
            imports = run(runtime, '-E', '-s', '-B', '-c',
                          'import ssl,sqlite3,ctypes,lzma,http.server,platform; print(platform.machine())', env=env)
            assert imports.stdout.strip() == manifest['arch']
            methods = [
                {'method':'initialize','params':{}},
                {'method':'tools/list','params':{}},
                {'method':'resources/read','params':{'uri':'ui://codex-bigfish/companion'}},
                {'method':'tools/call','params':{'name':'get_manifest','arguments':{}}},
                {'method':'tools/call','params':{'name':'get_packs','arguments':{}}},
                {'method':'tools/call','params':{'name':'get_frames','arguments':{'clip':'待机呼吸休闲','count':1}}},
            ]
            requests = '\n'.join(json.dumps(dict(jsonrpc='2.0', id=i+1, **v)) for i,v in enumerate(methods))+'\n'
            with local_host(runtime, app/'Contents/Resources', data, env):
                result = run('./run-server', cwd=package, env=env, input=requests)
                replies = [json.loads(line) for line in result.stdout.splitlines()]
                assert len(replies) == 6
                assert all('result' in reply and not reply['result'].get('isError') for reply in replies), replies
                assert replies[0]['result']['serverInfo']['version'] == manifest['version']
                assert len(replies[1]['result']['tools']) == 13
                assert '启用大肥鱼' in replies[2]['result']['contents'][0]['text']
                library = verify_library(replies[3]['result']['structuredContent'])
                packs = replies[4]['result']['structuredContent']
                assert packs['selected'] == 'builtin' and len(packs['manifest']['libraryClips']) == 106
                assert any(pack['id'] == 'builtin' and pack['clipCount'] == 106 for pack in packs['packs'])
                frames = replies[5]['result']['structuredContent']
                assert frames['total'] > 1 and len(frames['frames']) == 1
                assert next(iter(frames['frames'].values())).startswith('data:image/webp;base64,')
                media = run(runtime, '-E', '-s', '-B', '-c',
                            'import sys,json,subprocess; from pathlib import Path; '
                            'sys.path.insert(0,'+repr(str(app/'Contents/Resources/codex'))+'); '
                            'from media_runtime import resolve_ffmpeg; '
                            'p=resolve_ffmpeg(Path('+repr(str(app/'Contents/Resources'))+')); '
                            'license=subprocess.check_output([str(p),\"-hide_banner\",\"-L\"],text=True,stderr=subprocess.STDOUT); '
                            'assert \"GNU Lesser General Public License\" in " ".join(license.split()); '
                            'print(json.dumps({\"pinnedMediaChecksum\":True,\"mediaLicense\":\"LGPL\"}))', env=env)
                media_result = json.loads(media.stdout)
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
                assert discovery['settingsCapability'] and discovery['discoveredToolCount'] == 13
        return dict(arch=manifest['arch'], version=manifest['version'], runtimeExecuted=execute,
                    mountedAndDetached=True, relocatedSignature=True, independentOfDownload=True,
                    sandboxNativeDiscovery=discovery if execute else None,
                    canonicalLibrary=library if execute else None, bundledMedia=media_result if execute else None,
                    sha256=hashlib.sha256(dmg.read_bytes()).hexdigest(), bytes=dmg.stat().st_size)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('dmg', type=Path)
    parser.add_argument('--static-only', action='store_true', help='Do not execute foreign architecture binaries')
    args = parser.parse_args()
    print(json.dumps(verify(args.dmg.resolve(), not args.static_only), ensure_ascii=False, indent=2))
