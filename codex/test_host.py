import json
import tempfile
import unittest
import http.client
import threading
import io
import socket
import time
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
from host import ConfigStore, local_request, frame_path
from host import Host


class ConfigTests(unittest.TestCase):
    def test_defaults_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'settings.json'
            store = ConfigStore(p)
            self.assertEqual(store.value['scale'], 1)
            self.assertEqual(store.value['soundStates'], ['SUCCESS', 'ERROR'])
            store.update({'scale': 0.8, 'soundStates': ['APPROVAL'], 'webOverlay': True})
            self.assertEqual(ConfigStore(p).value['scale'], 0.8)
            self.assertEqual(ConfigStore(p).value['soundStates'], ['APPROVAL'])
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_invalid_settings_rejected_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp) / 'settings.json')
            for patch in [{'scale': True}, {'scale': float('nan')}, {'scale': 99},
                          {'bubbleMode': 'other'}, {'soundStates': ['NO']},
                          {'unknown': 1}, {'enabled': 'yes'}, {'balanceSource': '../'},
                          {'activityLevel': 'no'}, {'bubbleStates': [1]}]:
                with self.assertRaises(ValueError, msg=str(patch)):
                    store.update(patch)
            self.assertEqual(store.value['scale'], 1)

    def test_corrupt_file_preserved_and_defaults_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'settings.json'
            p.write_text('bad')
            store = ConfigStore(p)
            self.assertEqual(store.value['scale'], 1)
            self.assertEqual(p.read_text(), 'bad')


class BoundaryTests(unittest.TestCase):
    def test_local_origin_and_host(self):
        self.assertTrue(local_request('127.0.0.1', '127.0.0.1:8765', None, 8765))
        self.assertTrue(local_request('127.0.0.1', '127.0.0.1:8765', 'http://127.0.0.1:8765', 8765))
        self.assertFalse(local_request('127.0.0.1', 'evil.test:8765', None, 8765))
        self.assertFalse(local_request('127.0.0.1', '127.0.0.1:8765', 'https://evil.test', 8765))
        self.assertFalse(local_request('10.0.0.1', '127.0.0.1:8765', None, 8765))
        self.assertFalse(local_request('127.0.0.1', '127.0.0.1:1234', None, 8765))

    def test_manifest_frame_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'pet').mkdir()
            (root / 'pet/a.webp').touch()
            self.assertEqual(frame_path(root, {'a.webp'}, 'a.webp'), (root / 'pet/a.webp').resolve())
            for name in ['../settings.json', '/etc/passwd', 'b.webp']:
                with self.assertRaises(ValueError):
                    frame_path(root, {'a.webp'}, name)


class HTTPTests(unittest.TestCase):
    def test_partial_request_body_times_out(self):
        with tempfile.TemporaryDirectory() as tmp, patch('host.DATA', Path(tmp)):
            host = Host(Path(__file__).resolve().parents[1], '/nonexistent', request_timeout=0.1)
            worker = threading.Thread(target=host.server.serve_forever, daemon=True)
            worker.start()
            try:
                with socket.create_connection(('127.0.0.1', host.port), timeout=1) as sock:
                    raw = f'PATCH /plugins/dsh-dafeiyu/config HTTP/1.1\r\nHost: 127.0.0.1:{host.port}\r\nContent-Length: 50\r\n\r\n{{'
                    sock.sendall(raw.encode())
                    self.assertIn(b'408', sock.recv(4096))
            finally:
                host.server.shutdown()
                host.server.server_close()

    def test_snapshot_does_not_replay_historical_pulses(self):
        with tempfile.TemporaryDirectory() as tmp, patch('host.DATA', Path(tmp)):
            host = Host(Path(__file__).resolve().parents[1], '/nonexistent')
            try:
                host.send({'kind':'state','state':'THINKING'})
                host.send({'kind':'pulse','state':'ERROR'})
                snapshot = host.event_snapshot()
                self.assertEqual([m['kind'] for m in snapshot['messages']], ['state'])
                cursor = snapshot['cursor']
                host.send({'kind':'pulse','state':'SUCCESS'})
                self.assertEqual(host.event_snapshot(cursor)['messages'][0]['state'], 'SUCCESS')
                self.assertEqual(host.event_snapshot(10000)['messages'][0]['state'], 'THINKING')
            finally:
                host.server.server_close()

    def test_old_resumed_large_log_keeps_metadata_and_active_turn(self):
        with tempfile.TemporaryDirectory() as tmp, patch('host.DATA', Path(tmp) / 'data'), patch.dict('os.environ', {'CODEX_HOME': tmp}):
            logs = Path(tmp) / 'sessions/2020/01/01'
            logs.mkdir(parents=True)
            p = logs / 'rollout-old.jsonl'
            rows = [{'type': 'session_meta', 'payload': {'cwd': '/project', 'source': {'subagent': {}}}},
                    {'type': 'event_msg', 'payload': {'type': 'task_started'}}]
            p.write_text('\n'.join(json.dumps(r) for r in rows) + '\n' + json.dumps({'type': 'ignored', 'payload': {'padding': 'x' * (3*1024*1024)}}) + '\n')
            host = Host(Path(__file__).resolve().parents[1], '/nonexistent')
            try:
                host.poll_logs()
                self.assertEqual(host.registry.messages()[0]['state'], 'IDLE')
                # Historical unfinished work alone is not proof of a living task.
                with p.open('a') as f:
                    f.write(json.dumps({'type':'response_item','payload':{'type':'reasoning'}})+'\n')
                host.poll_logs()
                host.registry.include_subagents = True
                self.assertEqual(host.registry.messages()[0]['state'], 'THINKING')
                self.assertEqual(host.registry.active()[0][1].project, 'project')
            finally:
                host.server.server_close()

    def test_missing_and_entirely_invalid_sources_disconnect(self):
        with tempfile.TemporaryDirectory() as tmp, patch('host.DATA', Path(tmp) / 'data'), patch.dict('os.environ', {'CODEX_HOME': tmp}):
            host = Host(Path(__file__).resolve().parents[1], '/nonexistent')
            try:
                host.poll_logs()
                self.assertEqual(host.latest['state']['state'], 'DISCONNECTED')
                logs = Path(tmp) / 'sessions'
                logs.mkdir()
                p = logs / 'rollout-bad.jsonl'
                p.write_text('not-json\n')
                host.last_discovery = 0
                host.poll_logs()
                self.assertEqual(host.latest['state']['state'], 'DISCONNECTED')
                p.unlink()
                host.poll_logs()  # file disappearance must not escape
            finally:
                host.server.server_close()

    def test_repeated_corruption_disconnects_an_active_source(self):
        with tempfile.TemporaryDirectory() as tmp, patch('host.DATA', Path(tmp) / 'data'), patch.dict('os.environ', {'CODEX_HOME': tmp}):
            logs = Path(tmp) / 'sessions'
            logs.mkdir()
            p = logs / 'rollout.jsonl'
            p = logs / 'rollout-a.jsonl'
            p.write_text(json.dumps({'type':'event_msg','payload':{'type':'task_started'}})+'\n')
            host = Host(Path(__file__).resolve().parents[1], '/nonexistent')
            try:
                host.poll_logs()
                with p.open('a') as f:
                    f.write('bad\nbad\nbad\n')
                host.poll_logs()
                self.assertEqual(host.latest['state']['state'], 'DISCONNECTED')
            finally:
                host.server.server_close()

    def test_reap_waits_for_manual_close_reason(self):
        with tempfile.TemporaryDirectory() as tmp, patch('host.DATA', Path(tmp)):
            host = Host(Path(__file__).resolve().parents[1], '/nonexistent')
            try:
                proc = SimpleNamespace(stdout=io.StringIO(json.dumps({'kind':'closed','reason':'user'})+'\n'),
                                       stderr=io.StringIO(), stdin=io.StringIO(), poll=lambda: 0)
                host.process, host.host_pid = proc, 42
                proc.output_thread = threading.Thread(target=host.helper_output, args=(proc,))
                with host.lock:
                    proc.output_thread.start()
                    host.reap_helper()
                self.assertEqual(host.suppressed_pid, 42)
                self.assertEqual(host.crashes, 0)
            finally:
                host.server.server_close()

    def test_client_target_and_balance_invalidation(self):
        with tempfile.TemporaryDirectory() as tmp, patch('host.DATA', Path(tmp)):
            host = Host(Path(__file__).resolve().parents[1], '/nonexistent')
            try:
                self.assertEqual(host.open_target(), 'codex://')
                host.store.update({'clientTarget': 'web'})
                self.assertEqual(host.open_target(), host.url)
                host.balance = {'balances':[{'currency':'CNY','total':'10'}]}
                host.store.update({'balanceEnabled':False})
                self.assertEqual(host.balance_summary(), '')
            finally:
                host.server.server_close()

    def test_detects_actual_host_from_process_executable(self):
        with tempfile.TemporaryDirectory() as tmp, patch('host.DATA', Path(tmp)):
            host = Host(Path(__file__).resolve().parents[1], '/nonexistent')
            try:
                sample = '  42 /Applications/ChatGPT.app/Contents/MacOS/ChatGPT\n 99 /bin/bash\n'
                with patch('host.subprocess.run', return_value=SimpleNamespace(stdout=sample, returncode=0)):
                    self.assertEqual(host.detect_host(), 42)
            finally:
                host.server.server_close()

    def test_original_card_patch_and_foreign_origin(self):
        with tempfile.TemporaryDirectory() as tmp, patch('host.DATA', Path(tmp)):
            host = Host(Path(__file__).resolve().parents[1], '/nonexistent')
            worker = threading.Thread(target=host.server.serve_forever, daemon=True)
            worker.start()
            try:
                client = http.client.HTTPConnection('127.0.0.1', host.port, timeout=3)
                client.request('PATCH', '/plugins/dsh-dafeiyu/config', json.dumps({'scale': 0.8}), {'Content-Type': 'application/json'})
                result = client.getresponse()
                self.assertEqual(result.status, 200)
                self.assertEqual(json.loads(result.read())['scale'], 0.8)
                client.request('PATCH', '/plugins/dsh-dafeiyu/config', '{}', {'Origin': 'https://foreign.test'})
                result = client.getresponse()
                self.assertEqual(result.status, 403)
                result.read()
                client.close()
            finally:
                host.server.shutdown()
                host.server.server_close()


if __name__ == '__main__':
    unittest.main()
