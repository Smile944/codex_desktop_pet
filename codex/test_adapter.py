import json
import tempfile
import unittest
from pathlib import Path
from adapter import LogTail, SessionRegistry


def event(kind, **kw):
    return {'type': 'event_msg', 'payload': {'type': kind, **kw}}


def item(kind, **kw):
    return {'type': 'response_item', 'payload': {'type': kind, **kw}}


class TailTests(unittest.TestCase):
    def test_history_skipped_partial_line_and_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'a.jsonl'
            p.write_text(json.dumps(event('task_complete')) + '\n')
            tail = LogTail()
            self.assertEqual(tail.poll(p), [])
            with p.open('a') as f:
                f.write('{"type":"event_msg",')
            self.assertEqual(tail.poll(p), [])
            with p.open('a') as f:
                f.write('"payload":{"type":"task_started"}}\n')
            self.assertEqual(tail.poll(p), [event('task_started')])
            p.write_text(json.dumps(event('task_failed')) + '\n')
            self.assertEqual(tail.poll(p), [event('task_failed')])

    def test_bad_line_does_not_hide_next_valid_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'a.jsonl'
            p.touch()
            tail = LogTail()
            tail.poll(p)
            p.write_text('broken\n' + json.dumps(event('task_started')) + '\n')
            self.assertEqual(tail.poll(p), [event('task_started')])
            self.assertEqual(tail.invalid_lines, 1)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.r = SessionRegistry()

    def apply(self, record, sid='a'):
        return self.r.apply(sid, record)

    def state(self):
        return self.r.messages()[0]['state']

    def test_start_tool_result_complete(self):
        self.apply(event('task_started', turn_id='1'))
        self.assertEqual(self.state(), 'THINKING')
        self.apply(item('function_call', name='apply_patch', call_id='c'))
        self.assertEqual(self.state(), 'WORKING')
        self.assertEqual(self.r.messages()[0]['activity'], 'editing')
        self.apply(item('function_call_output', call_id='c', output='ok'))
        self.assertEqual(self.state(), 'THINKING')
        pulses = self.apply(event('task_complete', turn_id='1'))
        self.assertEqual(pulses[0]['state'], 'SUCCESS')
        self.assertEqual(self.state(), 'IDLE')

    def test_tool_failure_does_not_fail_turn(self):
        self.apply(event('task_started', turn_id='1'))
        self.apply(item('function_call', name='exec_command', call_id='c'))
        self.apply(item('function_call_output', call_id='c', output={'exit_code': 1}))
        self.assertEqual(self.state(), 'THINKING')

    def test_real_exec_output_block_reports_error_and_resumes_turn(self):
        self.apply(event('task_started'))
        self.apply(item('custom_tool_call', name='functions.exec', call_id='c'))
        output = [{'type':'input_text','text':'Script completed'},
                  {'type':'input_text','text':json.dumps({'chunk_id':'test','wall_time_seconds':0.1,'exit_code':7,'output':''})}]
        pulses = self.apply(item('custom_tool_call_output', call_id='c', output=output))
        self.assertEqual(pulses[0]['state'], 'ERROR')
        self.assertEqual(pulses[0]['resumeState'], 'THINKING')
        self.assertEqual(self.state(), 'THINKING')

    def test_blocking_input_waits_but_async_input_does_not(self):
        self.apply(event('task_started'))
        self.apply(item('function_call', name='functions.request_user_input', call_id='c'))
        self.assertEqual(self.state(), 'WAITING')
        self.apply(item('function_call_output', call_id='c', output='{}'))
        self.assertEqual(self.state(), 'THINKING')
        self.apply(item('function_call', name='functions.request_user_input_async', call_id='a'))
        self.assertEqual(self.state(), 'WORKING')

    def test_parallel_tool_output_does_not_clear_unanswered_input(self):
        self.apply(event('task_started'))
        self.apply(item('function_call', name='exec_command', call_id='a'))
        self.apply(item('function_call', name='request_user_input', call_id='b'))
        self.apply(item('function_call_output', call_id='a', output='{}'))
        self.assertEqual(self.state(), 'WAITING')
        self.apply(item('function_call_output', call_id='b', output='{}'))
        self.assertEqual(self.state(), 'THINKING')

    def test_concurrent_completion_resumes_other_work(self):
        self.apply(event('task_started', turn_id='1'))
        self.apply(event('task_started', turn_id='2'), 'b')
        pulse = self.apply(event('task_complete', turn_id='2'), 'b')[0]
        self.assertEqual(self.state(), 'THINKING')
        self.assertEqual(pulse['resumeState'], 'THINKING')

    def test_interrupt_and_unknown_never_success(self):
        self.apply(event('task_started', turn_id='1'))
        self.assertEqual(self.apply(event('future_event')), [])
        self.assertEqual(self.state(), 'THINKING')
        self.assertEqual(self.apply(event('turn_aborted')), [])
        self.assertEqual(self.state(), 'IDLE')

    def test_old_turn_completion_does_not_end_new_turn(self):
        self.apply(event('task_started', turn_id='new'))
        self.assertEqual(self.apply(event('task_complete', turn_id='old')), [])
        self.assertEqual(self.state(), 'THINKING')

    def test_child_session_ignored_unless_enabled(self):
        self.apply({'type': 'session_meta', 'payload': {'source': {'subagent': {'parent_thread_id': 'a'}}}}, 'child')
        self.apply(event('task_started'), 'child')
        self.assertEqual(self.state(), 'IDLE')
        self.r.include_subagents = True
        self.assertEqual(self.state(), 'THINKING')

    def test_explicit_approval_and_error(self):
        self.apply(event('task_started'))
        self.apply(event('permission_request'))
        self.assertEqual(self.state(), 'WAITING')
        pulses = self.apply(event('task_failed'))
        self.assertEqual(pulses[0]['state'], 'ERROR')
        self.assertEqual(self.state(), 'IDLE')

    def test_history_reconstruction_has_no_pulses(self):
        self.apply(event('task_started', turn_id='1'))
        self.assertEqual(self.r.apply('a', event('task_complete', turn_id='1'), replay=True), [])
        self.assertEqual(self.state(), 'IDLE')

    def test_malformed_fields_are_isolated(self):
        self.apply({'type': 'session_meta', 'payload': {'cwd': None}})
        self.apply(event('task_started'))
        for record in [item('function_call', name=None), item('function_call', name='x', call_id=[]),
                       {'type': 'response_item', 'payload': None},
                       item('function_call_output', call_id={})]:
            self.apply(record)
        self.apply(event('task_complete'))
        self.assertEqual(self.state(), 'IDLE')

    def test_excluded_child_does_not_send_approval_alert(self):
        self.apply({'type': 'session_meta', 'payload': {'source': {'subagent': {}}}}, 'child')
        self.apply(event('task_started'), 'child')
        self.assertEqual(self.apply(event('permission_request'), 'child'), [])


if __name__ == '__main__':
    unittest.main()
