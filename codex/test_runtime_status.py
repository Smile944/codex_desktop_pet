import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from runtime_status import read_runtime_status
from adapter import SessionRegistry, SessionState


class StatusTests(unittest.TestCase):
    def test_connection_creation_failure_is_reported_unavailable(self):
        with tempfile.NamedTemporaryFile() as socket, patch('runtime_status.StatusRPC',side_effect=OSError('closed')):
            self.assertEqual(read_runtime_status(socket.name)['status'],'unavailable')

    def test_authoritative_wait_is_visible_without_fresh_rollout_and_expires(self):
        registry=SessionRegistry()
        registry.sessions['one']=SessionState(thread_id='one')
        registry.apply_runtime_status({'one':{'type':'active','activeFlags':['waitingOnApproval']}})
        self.assertEqual(registry.messages()[0]['state'],'WAITING')
        self.assertEqual(registry.messages()[1]['tasks'][0]['message'],'等你呢')
        registry.apply_runtime_status({'one':None})
        self.assertEqual(registry.messages()[0]['state'],'IDLE')

    def test_missing_socket_does_not_start_another_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=read_runtime_status(Path(tmp)/'missing.sock')
            self.assertEqual(result['status'],'unavailable')

    def test_only_reads_metadata_and_captures_real_pending_flags(self):
        calls=[]
        def rpc(method,params=None):
            calls.append((method,params))
            if method=='thread/loaded/list':return {'data':['one','two']}
            if method=='thread/read':return {'thread':{'id':params['threadId'],'status':{'type':'active','activeFlags':['waitingOnApproval']}}}
            return {}
        result=read_runtime_status(rpc=rpc)
        self.assertEqual(result['threads']['one']['activeFlags'],['waitingOnApproval'])
        self.assertTrue(all(m in ('initialize','initialized','thread/loaded/list','thread/read') for m,_ in calls))
        self.assertTrue(all(p['includeTurns'] is False for m,p in calls if m=='thread/read'))


if __name__=='__main__':unittest.main()
