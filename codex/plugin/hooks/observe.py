"""Advisory hooks: no approval decisions, no tool arguments retained, no stdout."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

EVENTS = {'PermissionRequest','PostToolUse','PreModelRequest','Interrupt','Stop',
          'SessionEnd','UserPromptSubmit','SessionStart'}


def observe(payload):
    event = payload.get('hook_event_name')
    sid, turn = payload.get('session_id'), payload.get('turn_id','')
    if event not in EVENTS or not isinstance(sid,str) or not sid or len(sid)>200:
        return
    if not isinstance(turn,str) or len(turn)>200:
        return
    if event in ('PermissionRequest','PostToolUse') and not turn:
        return
    root = Path(os.environ.get('CODEX_BIGFISH_HOME',Path.home()/'Library/Application Support/Codex BigFish'))/'approval-hooks'
    name = hashlib.sha256(sid.encode()).hexdigest()
    target = root/(name+'.json')
    if event!='PermissionRequest' and not target.exists():return
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (root/(name+'.lock')).open('a') as lock:
        os.chmod(lock.name,0o600)
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:
            state=json.loads(target.read_text())
        except (OSError,ValueError):
            state={}
        if not isinstance(state,dict):state={}
        if event in ('PostToolUse','PreModelRequest','Interrupt','Stop') and turn and state.get('turn_id')!=turn:
            return
        pending=state.get('pending',{}) if state.get('turn_id')==turn else {}
        if not isinstance(pending,dict):pending={}
        if event in ('PermissionRequest','PostToolUse'):
            tool_input=payload.get('tool_input')
            if payload.get('tool_name')=='Bash' and isinstance(tool_input,dict):
                tool_input={'command':tool_input.get('command')}
            key=hashlib.sha256(json.dumps([payload.get('tool_name'),tool_input],sort_keys=True).encode()).hexdigest()
            if event=='PermissionRequest':pending[key]=min(100,pending.get(key,0)+1)
            elif key in pending:
                pending[key]-=1
                if pending[key]<=0:del pending[key]
        else:
            pending={}
        if not pending:
            target.unlink(missing_ok=True)
            return
        state=dict(session_id=sid,turn_id=turn,pending=pending,last_event=event,updated_at=time.time())
        fd, temporary=tempfile.mkstemp(dir=root,prefix='.event-')
        try:
            with os.fdopen(fd,'w') as output:json.dump(state,output)
            os.replace(temporary,target)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)


def main():
    try:
        data=sys.stdin.read(131073)
        if len(data)>131072:return
        payload=json.loads(data)
        if isinstance(payload,dict):observe(payload)
    except Exception:
        # An observation failure must never approve, deny, or block the user's tool.
        pass


if __name__=='__main__':main()
