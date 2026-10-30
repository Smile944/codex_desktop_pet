"""Read only approval hook metadata; never read commands or answer an approval."""
import json
import time


def pending_threads(data,since=None):
    pending={}
    root=data/'approval-hooks'
    if not root.is_dir():return pending
    for path in root.glob('*.json'):
        try:
            if path.is_symlink() or path.stat().st_size>65536:continue
            state=json.loads(path.read_text())
            sid,turn=state.get('session_id'),state.get('turn_id')
            if (isinstance(sid,str) and isinstance(turn,str) and state.get('pending') and
                    0<=time.time()-state['updated_at']<86400 and
                    (since is None or state['updated_at']>=since)):
                pending[sid]=turn
        except (OSError,ValueError,KeyError,TypeError,AttributeError):
            continue
    return pending


def apply_pending(registry,pending):
    for session in registry.sessions.values():
        session.hook_waiting=(session.state!='IDLE' and bool(session.thread_id) and
                              pending.get(session.thread_id)==session.turn)
