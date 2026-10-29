"""Observe an existing shared host only; never start a substitute runtime or resolve requests."""
import time
from pathlib import Path
from usage import UsageRPC


class StatusRPC(UsageRPC):
    ALLOWED={'initialize','initialized','thread/loaded/list','thread/read'}


def read_runtime_status(socket_path=None,rpc=None):
    owned=rpc is None
    try:
        if owned:
            path=Path(socket_path or Path.home()/'.codex/app-server-control/app-server-control.sock')
            if not path.exists():
                return {'status':'unavailable','reason':'shared_endpoint_missing','threads':{}}
            rpc=StatusRPC(timeout=3,proxy_socket=path)
        rpc('initialize',{'clientInfo':{'name':'bigfish_status_observer','version':'0.3.1'}})
        rpc('initialized',{})
        loaded=rpc('thread/loaded/list',{}).get('data',[])
        threads={}
        for tid in loaded[:100]:
            if not isinstance(tid,str):continue
            result=rpc('thread/read',{'threadId':tid,'includeTurns':False})
            status=result.get('thread',{}).get('status')
            if isinstance(status,dict):threads[tid]=status
        return {'status':'ready','threads':threads,'checkedAt':time.monotonic()}
    except (OSError,ValueError,TypeError,AttributeError):
        return {'status':'unavailable','reason':'shared_endpoint_unreachable','threads':{}}
    finally:
        if owned and rpc is not None:rpc.close()
