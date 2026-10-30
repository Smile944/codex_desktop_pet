"""Read-only Codex rollout adapter. No prompts/tool output are persisted."""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime


def message(kind, **payload):
    return dict(protocolVersion=1, kind=kind, timestamp=int(time.time() * 1000), **payload)


def tool_failed(output):
    """Recognize structured execution/MCP failures, never keywords in arbitrary output."""
    values = output if isinstance(output, list) else [output]
    for value in values:
        if isinstance(value, dict) and value.get('type') in ('input_text', 'text'):
            value = value.get('text')
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                continue
        if not isinstance(value, dict):
            continue
        if value.get('isError') is True:
            return True
        if type(value.get('exit_code')) is int and value['exit_code'] != 0 and isinstance(value.get('output'), str) and type(value.get('wall_time_seconds')) in (int, float):
            return True
    return False


class LogTail:
    """Byte offsets preserve partial UTF-8 lines; history is skipped on discovery."""
    def __init__(self):
        self.files = {}
        self.invalid_lines = 0
        self.valid_lines = {}
        self.status = {}
        self.consecutive_invalid = {}

    def poll(self, path, limit=4 * 1024 * 1024):
        path = Path(path)
        try:
            stat = path.stat()
            key = (stat.st_dev, stat.st_ino)
            previous = self.files.get(path)
            if previous is None:
                # Startup consumes metadata/state separately without emitting pulses.
                self.files[path] = (key, stat.st_size, b'')
                return []
            old_key, offset, pending = previous
            if key != old_key or stat.st_size < offset:
                offset, pending = 0, b''
                self.valid_lines[path] = 0
                self.consecutive_invalid[path] = 0
            with path.open('rb') as f:
                f.seek(offset)
                chunk = f.read(max(0, limit))
                offset = f.tell()
            lines = (pending + chunk).split(b'\n')
            self.files[path] = (key, offset, lines.pop())
            result = []
            for line in lines:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                    if isinstance(value, dict) and isinstance(value.get('type'), str):
                        result.append(value)
                        self.valid_lines[path] = self.valid_lines.get(path, 0) + 1
                        self.consecutive_invalid[path] = 0
                    else:
                        self.invalid_lines += 1
                        self.consecutive_invalid[path] = self.consecutive_invalid.get(path, 0) + 1
                except (ValueError, UnicodeError):
                    self.invalid_lines += 1
                    self.consecutive_invalid[path] = self.consecutive_invalid.get(path, 0) + 1
            self.status[path] = 'invalid' if self.consecutive_invalid.get(path, 0) >= 3 else 'readable'
            if len(self.files[path][2]) > 16 * 1024 * 1024:
                self.files[path] = (key, offset, b'')
                self.invalid_lines += 1
            return result
        except OSError:
            self.status[path] = 'unavailable'
            return []


@dataclass
class SessionState:
    state: str = 'IDLE'
    activity: str = ''
    turn: str = ''
    project: str = 'Codex'
    child: bool = False
    updated: float = 0
    pending: set = field(default_factory=set)
    waiting_calls: set = field(default_factory=set)
    approval_waiting: bool = False
    todos: list = field(default_factory=list)
    task: str = ''
    observed_live: bool = False
    thread_id: str = ''
    runtime_waiting: bool = False
    hook_waiting: bool = False

    @property
    def waiting(self):
        return self.runtime_waiting or self.hook_waiting


class SessionRegistry:
    def __init__(self):
        self.sessions = {}
        self.include_subagents = False
        self.quota_snapshot = None
        self.quota_at = 0

    def apply(self, sid, record, replay=False):
        if not isinstance(record, dict):
            return []
        s = self.sessions.setdefault(sid, SessionState())
        p = record.get('payload')
        if not isinstance(p, dict):
            return []
        kind = p.get('type', '')
        if not isinstance(kind, str):
            return []
        category = record.get('type')
        if category == 'event_msg' and kind == 'token_count' and isinstance(p.get('rate_limits'), dict):
            try:
                timestamp = record.get('timestamp')
                observed = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).timestamp() if isinstance(timestamp, str) else (0 if replay else time.time())
                if self.quota_at <= observed <= time.time()+60:
                    self.quota_snapshot, self.quota_at = p['rate_limits'], observed
            except (ValueError, TypeError, OverflowError):
                pass
            return []
        if category == 'session_meta':
            tid=p.get('id',p.get('session_id'))
            if isinstance(tid,str):s.thread_id=tid
            source = p.get('source', '')
            s.child = isinstance(source, dict) and 'subagent' in source
            s.child = s.child or p.get('thread_source') in ('subagent', 'agent')
            cwd = p.get('cwd')
            s.project = (Path(cwd).name if isinstance(cwd, str) else '') or 'Codex'
            return []
        if category == 'turn_context':
            cwd = p.get('cwd')
            if isinstance(cwd, str):
                s.project = Path(cwd).name or s.project
            return []
        if category == 'event_msg':
            if p.get('turn_id') is not None and not isinstance(p['turn_id'], str):
                return []
            if kind in ('task_started', 'turn_started'):
                s.state, s.activity, s.pending, s.todos = 'THINKING', '', set(), []
                s.waiting_calls, s.approval_waiting = set(), False
                s.turn = p.get('turn_id', '')
            elif kind in ('task_complete', 'turn_complete', 'task_failed', 'turn_aborted', 'task_aborted', 'task_interrupted'):
                if p.get('turn_id') and s.turn and p['turn_id'] != s.turn:
                    return []
                was_active = s.state != 'IDLE'
                s.state, s.activity, s.pending = 'IDLE', '', set()
                s.waiting_calls, s.approval_waiting = set(), False
                s.updated = time.time()
                if replay or not was_active or (s.child and not self.include_subagents):
                    return []
                if kind in ('task_complete', 'turn_complete', 'task_failed'):
                    state = 'ERROR' if kind == 'task_failed' else 'SUCCESS'
                    resume = self.messages()[0]
                    return [message('pulse', state=state, ttlMs=2000,
                                    message='这次的任务搞定啦~' if state == 'SUCCESS' else '任务好像遇到一点问题呢',
                                    detail=s.project + ' · Codex', resumeState=resume['state'],
                                    resumeActivity=resume.get('activity', ''),
                                    resumeMessage=resume['message'], resumeDetail=resume['detail'])]
                return []
            elif kind in ('permission_request', 'approval_requested', 'user_input_requested'):
                if s.state == 'IDLE':
                    return []
                s.state, s.activity = 'WAITING', ''
                s.approval_waiting = True
                s.updated = time.time()
                s.observed_live = s.observed_live or not replay
                return [] if replay or (s.child and not self.include_subagents) else [message('alert', alert='APPROVAL')]
            elif kind in ('permission_response', 'approval_resolved', 'user_input_response'):
                s.approval_waiting = False
                if s.state == 'WAITING':
                    s.state = 'WAITING' if s.waiting_calls else ('WORKING' if s.pending else 'THINKING')
            elif kind == 'agent_reasoning' and s.state != 'IDLE':
                if not s.waiting_calls and not s.approval_waiting:
                    s.state = 'THINKING'
            else:
                return []
        elif category == 'response_item':
            if s.state == 'IDLE':
                return []
            if kind in ('function_call', 'custom_tool_call'):
                name = p.get('name')
                call_id = p.get('call_id', name)
                if not isinstance(name, str) or not isinstance(call_id, str):
                    return []
                name = name.lower()
                s.pending.add(call_id)
                s.state = 'WORKING'
                s.activity = ('editing' if any(x in name for x in ('patch', 'write_file', 'edit_file')) else
                              'searching' if any(x in name for x in ('search', 'read_file', 'find', 'browse')) else
                              'commanding' if any(x in name for x in ('exec', 'command', 'stdin', 'bash')) else '')
                if name.rsplit('.', 1)[-1] == 'request_user_input':
                    s.waiting_calls.add(call_id)
                if s.waiting_calls or s.approval_waiting:
                    s.state, s.activity = 'WAITING', ''
                # Parse only structured plan fields, never persist tool arguments.
                if 'update_plan' in name:
                    try:
                        args = p.get('arguments', {})
                        args = json.loads(args) if isinstance(args, str) else args
                        rows = args.get('plan', [])
                        s.todos = [r for r in rows if isinstance(r, dict) and isinstance(r.get('step'), str)]
                    except (ValueError, AttributeError, TypeError):
                        pass
            elif kind in ('function_call_output', 'custom_tool_call_output'):
                if not isinstance(p.get('call_id'), str):
                    return []
                s.pending.discard(p['call_id'])
                s.waiting_calls.discard(p['call_id'])
                s.state = 'WAITING' if s.waiting_calls or s.approval_waiting else ('WORKING' if s.pending else 'THINKING')
                if not s.pending:
                    s.activity = ''
                if tool_failed(p.get('output')) and not replay and (not s.child or self.include_subagents):
                    s.observed_live, s.updated = True, time.time()
                    resume = self.messages()[0]
                    return [message('pulse', state='ERROR', ttlMs=1800, message='这一步好像没跑通呢',
                                    detail=s.project + ' · Codex', resumeState=resume['state'],
                                    resumeActivity=resume.get('activity', ''), resumeMessage=resume['message'],
                                    resumeDetail=resume['detail'])]
            elif kind == 'reasoning' and not s.pending:
                s.state, s.activity = ('WAITING' if s.approval_waiting else 'THINKING'), ''
            else:
                return []
        else:
            return []
        s.updated = time.time()
        s.observed_live = s.observed_live or not replay
        return []

    def active(self):
        return sorted(((sid, s) for sid, s in self.sessions.items()
                       if (s.state != 'IDLE' and s.observed_live or s.waiting) and (not s.child or self.include_subagents)),
                      key=lambda row: (row[1].state == 'WAITING' or row[1].waiting, row[1].updated), reverse=True)

    def apply_runtime_status(self,statuses):
        for s in self.sessions.values():
            status=statuses.get(s.thread_id,{})
            status=status if isinstance(status,dict) else {}
            flags=status.get('activeFlags') or []
            flags=flags if isinstance(flags,list) else []
            s.runtime_waiting=status.get('type')=='active' and any(f in flags for f in ('waitingOnApproval','waitingOnUserInput'))

    def messages(self):
        active = self.active()
        if active:
            _, s = active[0]
            copy = {'THINKING': '正在认真想下一步呢', 'WORKING': '正在继续处理任务呢', 'WAITING': '需要你确认一下后续呢'}
            detail = s.project + ' · Codex'
            if s.todos:
                done = sum(r.get('status') == 'completed' for r in s.todos)
                detail += f' · {done}/{len(s.todos)}'
            shown='WAITING' if s.waiting else s.state
            state = message('state', state=shown, activity='' if s.waiting else s.activity, message=copy[shown], detail=detail)
        else:
            state = message('state', state='IDLE', message='我在这儿等新任务哦', detail='Codex · 等待下一次任务')
        tasks = [dict(sessionId=sid, state='WAITING' if s.waiting else s.state, project=s.project, title=s.project,
                      message={'THINKING': '思考中', 'WORKING': '干活中', 'WAITING': '等你呢'}['WAITING' if s.waiting else s.state],
                      detail=s.project + ' · Codex') for sid, s in active]
        return [state, message('tasks', tasks=tasks)]
