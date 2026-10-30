"""Local BigFish host. Original Helper/UI; no model requests or screen access."""
import argparse
import fcntl
import json
import math
import mimetypes
import os
import queue
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from collections import deque
sys.dont_write_bytecode = True
from adapter import LogTail, SessionRegistry, message
from usage import parse_usage, read_usage, usage_summary
from scale_policy import MIN_SCALE, MAX_SCALE, normalize_saved_scale
from client_bundle import client_source
from runtime_status import read_runtime_status
from permission_hooks import pending_threads, apply_pending
from pet_packs import PackStore
from media_runtime import resolve_ffmpeg

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('CODEX_BIGFISH_HOME', Path.home() / 'Library/Application Support/Codex BigFish'))
DEFAULTS = dict(enabled=True, scale=1, bubbleScale=1, activityLevel='normal', reducedMotion=False,
                soundEnabled=True, soundStates=['SUCCESS', 'ERROR'], bubbleMode='always',
                bubbleStates=['SUCCESS', 'ERROR', 'WAITING'], includeSubagents=False,
                webOverlay=False, clientTarget='auto', balanceEnabled=True, balanceSource='auto',
                randomAnimations=True, petPack='builtin')


def validated(patch):
    if not isinstance(patch, dict) or set(patch) - set(DEFAULTS):
        raise ValueError('未知设置字段')
    for k, v in patch.items():
        if isinstance(DEFAULTS[k], bool):
            ok = isinstance(v, bool)
        elif k == 'petPack':
            ok = isinstance(v, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,80}', v))
        elif k in ('scale', 'bubbleScale'):
            lo, hi = (MIN_SCALE, MAX_SCALE) if k == 'scale' else (0.8, 1.2)
            ok = type(v) in (int, float) and math.isfinite(v) and lo <= v <= hi
        elif k in ('soundStates', 'bubbleStates'):
            choices = ('SUCCESS', 'ERROR', 'APPROVAL') if k == 'soundStates' else ('IDLE', 'THINKING', 'WORKING', 'WAITING', 'SUCCESS', 'ERROR')
            ok = isinstance(v, list) and len(v) <= len(choices) and all(isinstance(x, str) and x in choices for x in v)
        else:
            choices = dict(activityLevel=('quiet', 'normal', 'lively'), bubbleMode=('always', 'hidden', 'custom'),
                           clientTarget=('auto', 'web', 'desktop'), balanceSource=('auto', 'api-key', 'account'))
            ok = isinstance(v, str) and v in choices[k]
        if not ok:
            raise ValueError('无效设置: ' + k)
    return patch


class ConfigStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.value = json.loads(json.dumps(DEFAULTS))
        try:
            saved = json.loads(self.path.read_text())
            if isinstance(saved, dict) and 'scale' in saved:
                saved['scale'] = normalize_saved_scale(saved['scale'])
            self.value.update(validated(saved))
        except (OSError, ValueError, TypeError):
            pass

    def update(self, patch):
        validated(patch)
        with self.lock:
            value = {**self.value, **patch}
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            tmp = self.path.with_suffix('.tmp')
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as f:
                json.dump(value, f, ensure_ascii=False)
            os.replace(tmp, self.path)
            self.value = value
            return dict(value)


def local_request(remote, host, origin, port):
    allowed = {f'127.0.0.1:{port}', f'localhost:{port}'}
    return remote == '127.0.0.1' and host in allowed and (origin is None or origin == 'http://' + host)


def frame_path(assets, allowed, name):
    path = (assets / 'pet' / name).resolve()
    if name not in allowed or not path.is_relative_to((assets / 'pet').resolve()):
        raise ValueError('frame not allowlisted')
    return path


class Host:
    def __init__(self, resources, helper, port=0, standalone=False, snapshot=None, request_timeout=5):
        self.resources, self.helper_path = Path(resources), Path(helper)
        self.assets = self.resources / 'assets'
        self.store = ConfigStore(DATA / 'settings.json')
        try:
            ffmpeg = resolve_ffmpeg(self.resources)
        except (OSError, ValueError):
            ffmpeg = None
        self.pack_store = PackStore(self.assets, DATA, ffmpeg=ffmpeg)
        try:
            self.assets = self.pack_store.resolve(self.store.value['petPack'])
        except (OSError, ValueError):
            self.assets = self.pack_store.resolve('builtin')
            self.store.update({'petPack': 'builtin'})
        self.manifest = json.loads((self.assets / 'pet-manifest.json').read_text())
        self.frames = {f for c in self.manifest['clips'].values() for f in c['frames']}
        self.import_lock = threading.Lock()
        self.registry, self.tail = SessionRegistry(), LogTail()
        self.lock = threading.RLock()
        self.clients = set()
        self.process = None
        self.host_pid = None
        self.suppressed_pid = None
        self.standalone = standalone
        self.snapshot = snapshot
        self.stopping = threading.Event()
        self.latest = {}
        self.event_cursor = 0
        self.recent_events = deque(maxlen=128)
        self.request_timeout = request_timeout
        self.runtime_status={'status':'unavailable','threads':{}}
        self.runtime_status_at=0
        self.runtime_polling=False
        self.started = time.time()
        self.restart_at = 0
        self.crashes = 0
        self.last_signature = None
        self.events_seen = 0
        self.native_messages = queue.Queue()
        self.last_discovery = float('-inf')
        self.known_paths = set()
        self.source_health = 'waiting'
        self.balance = dict(status='loading', provider='codex', windows=[])
        self.balance_lock = threading.Lock()
        self.balance_at = 0
        self.server = ThreadingHTTPServer(('127.0.0.1', port), self.handler())
        self.server.daemon_threads = True
        self.port = self.server.server_port
        self.url = f'http://127.0.0.1:{self.port}'

    def handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            timeout = owner.request_timeout

            def log_message(self, *args):
                pass

            def reply(self, body, status=200, content_type='application/json; charset=utf-8'):
                if not isinstance(body, bytes):
                    body = json.dumps(body, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(body)

            def permitted(self):
                return local_request(self.client_address[0], self.headers.get('Host'), self.headers.get('Origin'), owner.port)

            def do_GET(self):
                if not self.permitted():
                    return self.reply({'error': 'local origin required'}, 403)
                url = urllib.parse.urlsplit(self.path)
                path = url.path
                endpoint = '/plugins/dsh-dafeiyu/'
                try:
                    if path == endpoint + 'config':
                        return self.reply(owner.store.value)
                    if path == endpoint + 'packs':
                        return self.reply(owner.pack_snapshot())
                    if path == endpoint + 'manifest':
                        return self.reply(owner.manifest)
                    if path == endpoint + 'balance':
                        owner.refresh_balance()
                        return self.reply(owner.balance)
                    if path == '/health':
                        return self.reply(dict(helperRunning=owner.process is not None and owner.process.poll() is None,
                                               active=len(owner.registry.active()), eventsSeen=owner.events_seen,
                                               invalidLines=owner.tail.invalid_lines, helperCrashes=owner.crashes,
                                               state=owner.latest.get('state', {}).get('state', 'DISCONNECTED'),
                                               approvalObserver=owner.runtime_status['status'],
                                               sourceHealth=owner.source_health, pid=os.getpid()))
                    if path == '/snapshot':
                        raw = urllib.parse.parse_qs(url.query).get('after', [None])[0]
                        after = int(raw) if raw is not None else None
                        if after is not None and after < 0:
                            raise ValueError('invalid event cursor')
                        return self.reply(owner.event_snapshot(after))
                    if path == endpoint + 'frame':
                        name = urllib.parse.parse_qs(url.query).get('frame', [''])[0]
                        with owner.lock:
                            frame = frame_path(owner.assets, owner.frames, name)
                            payload = frame.read_bytes()
                        return self.reply(payload, content_type='image/webp')
                    if path == endpoint + 'events':
                        return self.stream()
                    files = {'/': BASE / 'ui/index.html', '/wrapper.js': BASE / 'ui/wrapper.js',
                             '/react.js': BASE / 'vendor/react.production.min.js',
                             '/react-dom.js': BASE / 'vendor/react-dom.production.min.js'}
                    if path == '/client.js':
                        code = client_source(owner.resources, BASE / 'ui')
                        return self.reply(code.encode(), content_type='text/javascript; charset=utf-8')
                    if path in files:
                        typ = 'text/html; charset=utf-8' if path == '/' else 'text/javascript; charset=utf-8'
                        return self.reply(files[path].read_bytes(), content_type=typ)
                    self.reply({'error': 'not found'}, 404)
                except (OSError, ValueError):
                    self.reply({'error': 'not found'}, 404)

            def do_POST(self):
                if not self.permitted():
                    self.close_connection = True
                    return self.reply({'error': 'local origin required'}, 403)
                path = urllib.parse.urlsplit(self.path).path
                if path == '/plugins/dsh-dafeiyu/balance':
                    owner.refresh_balance(force=True)
                    return self.reply(owner.balance)
                if path not in ('/plugins/dsh-dafeiyu/config', '/plugins/dsh-dafeiyu/packs', '/plugins/dsh-dafeiyu/play'):
                    return self.reply({'error': 'not found'}, 404)
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 16384:
                        raise ValueError('请求过大或为空')
                    patch = json.loads(self.rfile.read(size))
                    if not isinstance(patch, dict):
                        raise ValueError('invalid request')
                    if path.endswith('/packs'):
                        if patch.get('action') == 'select' and set(patch) == {'action', 'id'}:
                            owner.select_pack(patch['id'])
                        elif patch.get('action') == 'import' and set(patch) == {'action', 'path'} and isinstance(patch['path'], str) and patch['path'].strip():
                            if not owner.import_lock.acquire(blocking=False):
                                return self.reply({'error': '正在导入，请等待完成后刷新角色包列表；请勿重复导入。'}, 409)
                            try:
                                owner.pack_store.import_pack(Path(patch['path']).expanduser())
                            finally:
                                owner.import_lock.release()
                        else:
                            raise ValueError('invalid pack action')
                        return self.reply(owner.pack_snapshot())
                    if path.endswith('/play'):
                        if set(patch) != {'clip'} or not isinstance(patch['clip'], str):
                            raise ValueError('invalid clip')
                        with owner.lock:
                            if patch['clip'] not in owner.manifest['clips']:
                                raise ValueError('unknown clip')
                            if not owner.store.value['enabled']:
                                return self.reply({'error': '请先在设置中启用大肥鱼，再点播动画。'}, 409)
                            if owner.suppressed_pid is not None and owner.suppressed_pid == owner.host_pid:
                                return self.reply({'error': '大肥鱼已手动关闭，请在设置中关闭并重新开启大肥鱼，再点播动画。'}, 409)
                            if owner.process is None or owner.process.poll() is not None:
                                return self.reply({'error': '桌面角色尚未运行，请确认 Codex 已打开并等待大肥鱼启动。'}, 409)
                            owner.send(message('play', clip=patch['clip']))
                        return self.reply({'ok': True})
                    validated(patch)
                    with owner.lock:
                        if 'petPack' in patch:
                            owner.select_pack(patch['petPack'])
                        was_enabled = owner.store.value['enabled']
                        value = owner.store.update(patch)
                        if value['enabled'] and not was_enabled:
                            owner.suppressed_pid = None
                            owner.crashes = 0
                            owner.restart_at = 0
                        owner.registry.include_subagents = value['includeSubagents']
                        if set(patch) & {'balanceEnabled', 'balanceSource', 'enabled'}:
                            owner.balance_at = 0
                            owner.send(message('balance', summary=''))
                        owner.last_signature = None
                        owner.send(message('config', **value, openUrl=owner.open_target(), openLabel='打开 Codex'))
                    self.reply(value)
                except (TimeoutError, socket.timeout):
                    self.close_connection = True
                    try:
                        self.reply({'error': '请求读取超时'}, 408)
                    except OSError:
                        pass
                except (ValueError, TypeError, UnicodeError, OSError) as error:
                    self.close_connection = True
                    self.reply({'error': str(error) or '设置值无效'}, 400)

            do_PATCH = do_POST

            def stream(self):
                q = queue.Queue(maxsize=64)
                with owner.lock:
                    owner.clients.add(q)
                    initial = list(owner.latest.values())
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.close_connection = True
                try:
                    for event in initial:
                        self.wfile.write(('data: ' + json.dumps(event, ensure_ascii=False) + '\n\n').encode())
                    self.wfile.flush()
                    while not owner.stopping.is_set():
                        try:
                            event = q.get(timeout=10)
                            payload = 'data: ' + json.dumps(event, ensure_ascii=False) + '\n\n'
                        except queue.Empty:
                            payload = ': heartbeat\n\n'
                        self.wfile.write(payload.encode())
                        self.wfile.flush()
                except (OSError, ValueError):
                    pass
                finally:
                    with owner.lock:
                        owner.clients.discard(q)

        return Handler

    def pack_snapshot(self):
        with self.lock:
            return {'packs': self.pack_store.list(), 'selected': self.store.value['petPack'], 'manifest': self.manifest}

    def select_pack(self, pack_id):
        with self.lock:
            assets = self.pack_store.resolve(pack_id)
            manifest = json.loads((assets / 'pet-manifest.json').read_text())
            frames = {f for c in manifest['clips'].values() for f in c['frames']}
            if pack_id == self.store.value['petPack']:
                return
            self.store.update({'petPack': pack_id})
            running = self.process is not None
            if running:
                self.stop_helper()
            self.assets, self.manifest, self.frames = assets, manifest, frames
            self.send(message('pack', selected=pack_id))
            if running and self.store.value['enabled']:
                self.start_helper()

    def send(self, msg):
        with self.lock:
            self.event_cursor += 1
            self.recent_events.append((self.event_cursor, msg))
            if msg['kind'] not in ('pulse', 'alert', 'play'):
                self.latest[msg['kind']] = msg
            if self.process is not None and self.process.poll() is None:
                try:
                    self.process.stdin.write(json.dumps(msg, ensure_ascii=False) + '\n')
                    self.process.stdin.flush()
                except (OSError, ValueError):
                    pass
            for q in list(self.clients):
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    self.clients.discard(q)

    def event_snapshot(self, after=None):
        with self.lock:
            if after is None or after > self.event_cursor or not self.recent_events or after < self.recent_events[0][0]-1:
                messages = list(self.latest.values())
            else:
                messages = [msg for seq, msg in self.recent_events if seq > after]
            return {'cursor': self.event_cursor, 'messages': messages}

    def refresh_balance(self, force=False):
        if not self.balance_lock.acquire(blocking=False):
            return
        try:
            if not force and time.monotonic() - self.balance_at < 60:
                return
            self.balance_at = time.monotonic()
            config_revision = tuple(self.store.value[k] for k in ('enabled', 'balanceEnabled', 'balanceSource'))
            source = self.store.value['balanceSource']
            if not self.store.value['balanceEnabled'] or not self.store.value['enabled']:
                self.balance = dict(status='disabled', provider='codex', windows=[])
            else:
                # Legacy config value "api-key" now selects Codex session records;
                # keeping the key avoids losing existing companion preferences.
                if source == 'api-key':
                    self.balance = self.session_usage()
                else:
                    try:
                        self.balance = read_usage()
                    except (OSError, ValueError, TypeError):
                        if source == 'account':
                            raise
                        self.balance = self.session_usage()
            if config_revision != tuple(self.store.value[k] for k in ('enabled', 'balanceEnabled', 'balanceSource')):
                self.balance_at = 0
                return
            self.send(message('balance', **self.balance, summary=self.balance_summary()))
        except (OSError, ValueError, KeyError, TypeError):
            self.balance = dict(status='error', provider='codex', windows=[], error='暂时无法读取 Codex 额度，请确认 Codex 已登录后刷新。')
            self.send(message('balance', **self.balance, summary=''))
        finally:
            self.balance_lock.release()

    def balance_summary(self):
        return usage_summary(self.balance) if self.store.value['balanceEnabled'] and self.balance.get('status') == 'ready' else ''

    def session_usage(self):
        if self.registry.quota_snapshot is None or time.time()-self.registry.quota_at > 300:
            raise OSError('No recent Codex quota event')
        result = parse_usage({'rateLimits': self.registry.quota_snapshot})
        result.update(source='session', checkedAt=int(self.registry.quota_at*1000))
        return result

    def open_target(self):
        return self.url if self.store.value['clientTarget'] == 'web' else 'codex://'

    def detect_host(self):
        if self.standalone:
            return -1
        try:
            result = subprocess.run(['/bin/ps', '-axo', 'pid=,comm='], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                for row in result.stdout.splitlines():
                    parts = row.strip().split(None, 1)
                    if len(parts) == 2 and parts[1] in ('/Applications/ChatGPT.app/Contents/MacOS/ChatGPT', '/Applications/Codex.app/Contents/MacOS/Codex'):
                        return int(parts[0])
            return None
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
            return None

    def start_helper(self):
        env = dict(os.environ, DSH_DAFEIYU_ASSET_ROOT=str(self.assets),
                   DSH_DAFEIYU_LAYOUT_PATH=str(DATA / 'layout.json'),
                   DSH_DAFEIYU_WEBUI_URL='codex://', DSH_DAFEIYU_OPEN_LABEL='打开 Codex',
                   CODEX_BIGFISH_HOST_NAME='Codex')
        # Saved config, rather than inherited DSH process settings, is authoritative.
        for k in list(env):
            if k.startswith('DSH_DAFEIYU_') and k not in ('DSH_DAFEIYU_ASSET_ROOT', 'DSH_DAFEIYU_LAYOUT_PATH', 'DSH_DAFEIYU_WEBUI_URL', 'DSH_DAFEIYU_OPEN_LABEL'):
                env.pop(k)
        args = [str(self.helper_path)]
        if self.snapshot:
            args += ['--snapshot', str(self.snapshot)]
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, bufsize=1, env=env)
        self.process = proc
        proc.close_reason = None
        proc.output_thread = threading.Thread(target=self.helper_output, args=(proc,), daemon=True)
        proc.output_thread.start()
        threading.Thread(target=self.helper_errors, args=(proc,), daemon=True).start()
        self.send(message('config', **self.store.value, openUrl=self.open_target(), openLabel='打开 Codex'))
        for msg in (self.latest.get('state'), self.latest.get('tasks')):
            if msg is None:
                continue
            self.send(msg)
        self.send(message('balance', **self.balance, summary=self.balance_summary()))

    def helper_errors(self, proc):
        # Drain stderr without retaining arbitrary native messages or triggering pipe deadlocks.
        for line in proc.stderr:
            if 'Unable to locate BigFish assets' in line:
                print('helper: assets unavailable', file=sys.stderr, flush=True)

    def helper_output(self, proc):
        for line in proc.stdout:
            try:
                data = json.loads(line)
                if not isinstance(data, dict):
                    continue
                if data.get('kind') == 'closed':
                    # Never wait for owner.lock: the main loop may be reaping this process.
                    proc.close_reason = data.get('reason')
                elif data.get('kind') == 'settings':
                    self.native_messages.put({k: v for k, v in data.items() if k in DEFAULTS})
            except (ValueError, OSError, TypeError):
                pass

    def reap_helper(self):
        proc = self.process
        if proc is None or proc.poll() is None:
            return
        if hasattr(proc, 'output_thread'):
            proc.output_thread.join(timeout=2)
        if getattr(proc, 'close_reason', None) == 'user':
            self.suppressed_pid = self.host_pid
        else:
            self.crashes += 1
            self.restart_at = time.monotonic() + min(30, 2 ** self.crashes)
        self.stop_helper()

    def drain_native(self):
        while True:
            try:
                patch = self.native_messages.get_nowait()
            except queue.Empty:
                break
            try:
                if patch:
                    self.store.update(patch)
                    self.send(message('config', **self.store.value, openUrl=self.open_target(), openLabel='打开 Codex'))
            except (OSError, ValueError):
                pass

    def stop_helper(self):
        proc, self.process = self.process, None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.stdin.write(json.dumps(message('shutdown')) + '\n')
                proc.stdin.flush()
                proc.wait(timeout=3)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            proc.terminate()
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                stream.close()
            except OSError:
                pass

    def poll_logs(self):
        sessions = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'sessions'
        if time.monotonic() - self.last_discovery > 2:
            self.last_discovery = time.monotonic()
            try:
                self.known_paths.update(sessions.rglob('rollout-*.jsonl'))
            except OSError:
                pass
        for path in list(self.known_paths):
            if path not in self.tail.files:
                try:
                    stat = path.stat()
                except OSError:
                    self.tail.status[path] = 'unavailable'
                    continue
                self.tail.files[path] = ((stat.st_dev, stat.st_ino), 0, b'')
                remaining = stat.st_size
                # Read complete metadata and turn boundaries. Historical active state is
                # not displayed until fresh live activity confirms that session is alive.
                while remaining > 0:
                    before = self.tail.files[path][1]
                    for record in self.tail.poll(path, min(remaining, 4 * 1024 * 1024)):
                        self.registry.apply(path.stem, record, replay=True)
                    consumed = self.tail.files[path][1] - before
                    if consumed <= 0:
                        break
                    remaining -= consumed
                records = self.tail.poll(path)
            else:
                records = self.tail.poll(path)
            for record in records:
                for pulse in self.registry.apply(path.stem, record):
                    self.send(pulse)
                if record.get('type') in ('event_msg', 'response_item'):
                    self.events_seen += 1
        statuses=self.runtime_status.get('threads',{}) if self.runtime_status['status']=='ready' and time.monotonic()-self.runtime_status.get('checkedAt',0)<12 else {}
        self.registry.apply_runtime_status(statuses)
        previous={sid for sid,s in self.registry.sessions.items() if s.hook_waiting}
        apply_pending(self.registry,pending_threads(DATA,since=self.started))
        if any(s.hook_waiting and sid not in previous and (not s.child or self.registry.include_subagents)
               for sid,s in self.registry.sessions.items()):
            self.send(message('alert',alert='APPROVAL'))
        current = self.registry.messages()
        healthy = [p for p in self.known_paths if self.tail.status.get(p) == 'readable' and self.tail.valid_lines.get(p, 0)]
        active_unavailable = any(self.tail.status.get(p) in ('unavailable', 'invalid') and
                                 self.registry.sessions.get(p.stem) and self.registry.sessions[p.stem].state != 'IDLE'
                                 for p in self.known_paths)
        self.source_health = 'ready' if healthy and not active_unavailable else 'unavailable'
        if self.source_health != 'ready':
            current = [message('state', state='DISCONNECTED', message='暂时无法读取 Codex 任务状态', detail='请检查本地会话数据是否可用'), message('tasks', tasks=[])]
        signature = json.dumps([{k: v for k, v in m.items() if k != 'timestamp'} for m in current], sort_keys=True)
        if signature != self.last_signature:
            self.last_signature = signature
            for msg in current:
                self.send(msg)

    def run(self):
        DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
        (DATA / 'endpoint.json').write_text(json.dumps(dict(url=self.url, pid=os.getpid())))
        self.registry.include_subagents = self.store.value['includeSubagents']
        self.send(message('config', **self.store.value))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        print(json.dumps(dict(ready=True, url=self.url)), flush=True)
        last_host_check = 0
        try:
            while not self.stopping.wait(0.4):
                with self.lock:
                    if time.monotonic() - last_host_check > 2:
                        last_host_check = time.monotonic()
                        pid = self.detect_host()
                        if pid != self.host_pid:
                            self.stop_helper()
                            self.host_pid = pid
                            self.suppressed_pid = None
                            self.crashes = 0
                            if pid is None:
                                self.registry = SessionRegistry()
                                self.registry.include_subagents = self.store.value['includeSubagents']
                    self.poll_logs()
                    if not self.runtime_polling and time.monotonic()-self.runtime_status_at>5:
                        self.runtime_polling=True
                        self.runtime_status_at=time.monotonic()
                        def observe():
                            try:self.runtime_status=read_runtime_status()
                            finally:self.runtime_polling=False
                        threading.Thread(target=observe,daemon=True).start()
                    self.reap_helper()
                    self.drain_native()
                    if time.monotonic() - self.balance_at >= 60 and not self.balance_lock.locked():
                        threading.Thread(target=self.refresh_balance, daemon=True).start()
                    if not self.store.value['enabled']:
                        self.stop_helper()
                    elif self.host_pid is not None and self.host_pid != self.suppressed_pid and self.process is None and self.crashes < 4 and time.monotonic() >= self.restart_at:
                        self.start_helper()
        finally:
            self.stopping.set()
            self.stop_helper()
            self.server.shutdown()
            self.server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--resources', required=True)
    parser.add_argument('--helper', required=True)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--standalone', action='store_true')
    parser.add_argument('--snapshot')
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (DATA / 'host.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        host = Host(args.resources, args.helper, args.port, args.standalone, args.snapshot)
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: host.stopping.set())
        host.run()


if __name__ == '__main__':
    main()
