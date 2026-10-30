import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import io
from contextlib import redirect_stdout
from unittest.mock import patch
from adapter import SessionRegistry

SCRIPT = Path(__file__).parent/'plugin/hooks/observe.py'


class HookTests(unittest.TestCase):
    def test_restarted_host_does_not_revive_historical_pending_approval(self):
        from permission_hooks import pending_threads,apply_pending
        import time
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'approval-hooks';folder.mkdir()
            started=time.time()
            state={'session_id':'thread','turn_id':'t','pending':{'old':1},'updated_at':started-10}
            path=folder/'old.json';path.write_text(json.dumps(state))
            registry=SessionRegistry()
            registry.apply('rollout',{'type':'session_meta','payload':{'id':'thread'}},replay=True)
            registry.apply('rollout',{'type':'event_msg','payload':{'type':'task_started','turn_id':'t'}},replay=True)
            apply_pending(registry,pending_threads(root,since=started))
            self.assertEqual(registry.messages()[0]['state'],'IDLE')
            state['updated_at']=time.time();path.write_text(json.dumps(state))
            apply_pending(registry,pending_threads(root,since=started))
            self.assertEqual(registry.messages()[0]['state'],'WAITING')

    def test_user_config_merge_preserves_other_hooks_and_never_adds_trust(self):
        from install_hooks import install
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            config=root/'.codex/hooks.json';config.parent.mkdir()
            other={'hooks':[{'type':'command','command':'echo existing'}]}
            config.write_text(json.dumps({'hooks':{'Stop':[other]},'description':'keep'}))
            with patch.dict('os.environ',{'CODEX_HOME':str(config.parent)}),redirect_stdout(io.StringIO()), \
                 patch('install_hooks.hooks_supported',return_value=True):
                install(root);first=json.loads(config.read_text());install(root)
            self.assertEqual(json.loads(config.read_text()),first)
            self.assertEqual(first['hooks']['Stop'][0],other)
            self.assertEqual(first['description'],'keep')
            self.assertNotIn('trusted_hash',config.read_text())
            self.assertTrue(list(config.parent.glob('hooks.json.backup-*')))

    def test_unsupported_host_does_not_create_user_hook_config(self):
        from install_hooks import install
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.dict('os.environ',{'CODEX_HOME':str(root/'.codex')}), \
                 patch('install_hooks.hooks_supported',return_value=False),redirect_stdout(io.StringIO()):
                install(root)
            self.assertFalse((root/'.codex/hooks.json').exists())

    def test_observer_never_decides_and_tracks_concurrent_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            def send(event, command='one', turn='t'):
                payload=dict(hook_event_name=event, session_id='thread', turn_id=turn,
                             tool_name='Bash', tool_input={'command':command})
                if event=='PermissionRequest':
                    payload['tool_input']['description']='approval reason, absent from tool result'
                p=subprocess.run([sys.executable,'-B',str(SCRIPT)],input=json.dumps(payload),
                                 env={**__import__('os').environ,'CODEX_BIGFISH_HOME':tmp},
                                 capture_output=True,text=True,check=True)
                self.assertEqual(p.stdout,'')
                self.assertEqual(p.stderr,'')
            send('PermissionRequest');send('PermissionRequest','two')
            from permission_hooks import pending_threads
            self.assertIn('thread',pending_threads(Path(tmp)))
            send('PostToolUse')
            self.assertIn('thread',pending_threads(Path(tmp)))
            send('PostToolUse','two')
            self.assertNotIn('thread',pending_threads(Path(tmp)))
            for end in ('PreModelRequest','Interrupt','Stop','SessionEnd','UserPromptSubmit'):
                send('PermissionRequest');send(end)
                self.assertNotIn('thread',pending_threads(Path(tmp)))
            send('PermissionRequest',turn='new')
            send('PostToolUse',turn='old')
            self.assertIn('thread',pending_threads(Path(tmp)))
            files=list((Path(tmp)/'approval-hooks').glob('*.json'))
            self.assertNotIn('command',files[0].read_text())

    def test_nonapproval_activity_does_not_accumulate_state_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=subprocess.run([sys.executable,'-B',str(SCRIPT)],input=json.dumps({
                'hook_event_name':'PostToolUse','session_id':'never-approved','turn_id':'t'}),
                env={**__import__('os').environ,'CODEX_BIGFISH_HOME':tmp},text=True,capture_output=True)
            self.assertEqual(p.returncode,0)
            self.assertEqual(list(Path(tmp).iterdir()),[])

    def test_overlay_does_not_change_log_state_and_respects_children(self):
        from permission_hooks import apply_pending
        registry=SessionRegistry()
        registry.apply('rollout',{'type':'session_meta','payload':{'id':'thread'}})
        registry.apply('rollout',{'type':'event_msg','payload':{'type':'task_started','turn_id':'t'}})
        apply_pending(registry,{'thread':'t'})
        self.assertEqual(registry.messages()[0]['state'],'WAITING')
        apply_pending(registry,{})
        self.assertEqual(registry.messages()[0]['state'],'THINKING')
        registry.sessions['rollout'].child=True
        apply_pending(registry,{'thread':'t'})
        self.assertEqual(registry.messages()[0]['state'],'IDLE')

    def test_invalid_or_oversize_input_is_advisory(self):
        for data in ('not json', '{}', 'x'*140000):
            p=subprocess.run([sys.executable,'-B',str(SCRIPT)],input=data,text=True,capture_output=True)
            self.assertEqual(p.returncode,0)
            self.assertEqual(p.stdout,'')


if __name__=='__main__':unittest.main()
