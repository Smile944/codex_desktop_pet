"""Real app-server approval client for manual decline/cancel verification only.

Never approves commands. No response is sent until a human clicks a local button.
No mock approvals or Hook payloads are injected into the companion.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from usage import CLI_CANDIDATES


class ApprovalGate:
    def __init__(self,send):
        self.send=send
        self.pending=None
        self.decision=None
        self.lock=threading.RLock()

    def receive(self,request):
        if request.get('method')!='item/commandExecution/requestApproval':
            raise ValueError('Unsupported approval method')
        with self.lock:
            if self.pending is not None:raise ValueError('Concurrent approval is not supported by this one-shot test')
            self.pending=request

    def decide(self,request_id,decision):
        with self.lock:
            if self.pending is None or self.pending['id']!=request_id:
                raise ValueError('This request is no longer pending')
            allowed=self.pending['params'].get('availableDecisions')
            if decision not in ('decline','cancel') or (allowed is not None and decision not in allowed):
                raise ValueError('This decision is not available; no response was sent')
            self.send({'id':request_id,'result':{'decision':decision}})
            self.decision=decision
            self.pending=None

    def resolve(self,request_id=None):
        with self.lock:
            if self.pending is not None and (request_id is None or self.pending['id']==request_id):
                self.pending=None


class Client:
    def __init__(self):
        cli=next((p for p in CLI_CANDIDATES if Path(p).is_file()),None)
        if cli is None:raise OSError('Codex CLI is missing')
        self.process=subprocess.Popen([cli,'app-server','--listen','stdio://'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1,start_new_session=True)
        self.write_lock=threading.Lock()
        self.lock=threading.RLock()
        self.responses={}
        self.next_id=0
        self.gate=ApprovalGate(self.send)
        self.thread_id=None
        self.turn_id=None
        self.phase='正在连接本机 Codex…'
        self.error=None
        self.command_status=None
        self.turn_status=None
        self.resolved=False
        self.approval_request_id=None
        self.saw_waiting=False
        self.messages=[]
        threading.Thread(target=self.read,daemon=True).start()

    def send(self,value):
        with self.write_lock:
            self.process.stdin.write(json.dumps(value)+'\n')
            self.process.stdin.flush()

    def call(self,method,params):
        with self.lock:
            self.next_id+=1;request_id='manual-'+str(self.next_id)
            event=threading.Event();box={};self.responses[request_id]=(event,box)
        self.send({'id':request_id,'method':method,'params':params})
        if not event.wait(30):raise TimeoutError(method+' timed out')
        if 'error' in box:raise OSError(str(box['error']))
        return box.get('result',{})

    def read(self):
        try:
            for line in self.process.stdout:
                packet=json.loads(line)
                if 'method' not in packet:
                    with self.lock:waiting=self.responses.pop(packet.get('id'),None)
                    if waiting:
                        event,box=waiting;box.update(packet);event.set()
                    continue
                method=packet['method'];params=packet.get('params',{})
                if 'id' in packet:
                    if method=='item/commandExecution/requestApproval' and params.get('threadId')==self.thread_id:
                        self.gate.receive(packet)
                        self.approval_request_id=packet['id']
                        self.error=None
                        self.phase='真实审批已到达，请先观察桌宠 WAITING，再选择下方操作。'
                    else:
                        self.error='收到本验收器不支持的请求；未执行或批准任何操作：'+method
                        self.send({'id':packet['id'],'error':{'code':-32601,'message':'Unsupported manual verification request'}})
                    continue
                if params.get('threadId')!=self.thread_id:continue
                if method=='serverRequest/resolved':
                    if params.get('requestId')==self.approval_request_id:
                        self.gate.resolve(self.approval_request_id)
                        self.resolved=True
                elif method=='item/agentMessage/delta':
                    self.messages.append(params.get('delta',''))
                elif method=='item/completed':
                    item=params.get('item',{})
                    if item.get('type')=='commandExecution':self.command_status=item.get('status')
                elif method=='turn/completed':
                    self.gate.resolve()
                    self.turn_status=params.get('turn',{}).get('status')
                    self.phase='本轮已结束：'+str(self.turn_status)
                elif method=='error':self.error=str(params.get('error',{}))
        except (OSError,ValueError) as exc:self.error=str(exc)
        finally:self.gate.resolve()

    def start_test(self):
        try:
            self.call('initialize',{'clientInfo':{'name':'bigfish_manual_decline','version':'1'},
                                    'capabilities':{'experimentalApi':True}})
            self.send({'method':'initialized'})
            workspace=Path.home()/'Library/Application Support/Codex BigFish/approval-test-workspace'
            workspace.mkdir(parents=True,exist_ok=True)
            probe=workspace/'bigfish-decline-probe.sh'
            probe.write_text('#!/bin/sh\n/usr/bin/printf BIGFISH_DECLINE_TEST\n')
            probe.chmod(0o755)
            result=self.call('thread/start',{'cwd':str(workspace),'approvalPolicy':'untrusted',
                                            'approvalsReviewer':'user','sandbox':'read-only'})
            self.thread_id=result['thread']['id']
            self.phase='正在等待模型发起真实审批，请稍候；不会自动响应审批。'
            prompt=('这是桌宠真实拒绝审批验收。仅尝试一次执行 ./bigfish-decline-probe.sh。'
                    '脚本已经准备好且只打印标记。使用 exec_command 的默认沙箱权限（use_default），不要申请 require_escalated。'
                    '当前仅本测试线程为 untrusted 人工审批策略，等待客户端对脚本的普通审批。'
                    '不要读取或改写脚本，不要读其他文件。用户拒绝后不要重试，不调用其他工具，'
                    '仅回复已收到拒绝并正常结束本轮。不要读取个人文件，不写文件，不联网。')
            turn=self.call('turn/start',{'threadId':self.thread_id,'input':[{'type':'text','text':prompt}]})
            self.turn_id=turn['turn']['id']
        except (OSError,KeyError,TimeoutError) as exc:self.error=str(exc)

    def view(self):
        hook_waiting=False;pet_state=None
        if self.thread_id:
            import urllib.request
            from permission_hooks import pending_threads
            data=Path.home()/'Library/Application Support/Codex BigFish'
            hook_waiting=self.thread_id in pending_threads(data)
            self.saw_waiting=self.saw_waiting or hook_waiting
            try:
                ep=json.loads((data/'endpoint.json').read_text())
                # Only use a bounded loopback endpoint created by the installed companion.
                from urllib.parse import urlsplit
                url=urlsplit(ep['url'])
                if url.scheme=='http' and url.hostname=='127.0.0.1' and url.port and not url.username and not url.path:
                    with urllib.request.urlopen(ep['url']+'/snapshot',timeout=1) as response:snapshot=json.load(response)
                    for message in snapshot['messages']:
                        if message['kind']=='tasks':
                            for task in message.get('tasks',[]):
                                if task['sessionId'].endswith(self.thread_id):pet_state=task['state']
            except (OSError,ValueError,KeyError):pass
        with self.gate.lock:
            pending=self.gate.pending
            request_id=pending['id'] if pending else None
            params=pending['params'] if pending else {}
            decisions=params.get('availableDecisions')
            return dict(phase=self.phase,error=self.error,requestId=request_id,command=params.get('command'),
                canDecline=pending is not None and (decisions is None or 'decline' in decisions),
                availableDecisions=decisions,
                canCancel=pending is not None and (decisions is None or 'cancel' in decisions),
                decisionSent=self.gate.decision,requestResolved=self.resolved,commandStatus=self.command_status,
                turnStatus=self.turn_status,hookWaiting=hook_waiting,petTaskState=pet_state,
                sawWaiting=self.saw_waiting,reply=''.join(self.messages)[-3000:])

    def close(self):
        try:
            if self.thread_id and self.turn_id and self.turn_status is None:
                self.call('turn/interrupt',{'threadId':self.thread_id,'turnId':self.turn_id})
        finally:
            self.process.terminate()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()


PAGE='''<!doctype html><meta charset="utf-8"><title>大肥鱼 · 真实拒绝审批验收</title>
<style>body{font:17px system-ui;max-width:760px;margin:40px auto;padding:0 24px}pre{white-space:pre-wrap;background:#eee;padding:16px;border-radius:10px}button{font:inherit;margin:12px 12px 12px 0;padding:12px}small{color:#555}</style>
<h1>真实拒绝审批验收</h1><p>这是独立的验收客户端，连接本机真实 Codex。没有“允许”按钮，不会自动作出决定。</p>
<p id="phase">连接中…</p><pre id="command">等待真实审批请求…</pre>
<p>真实审批到达后，先观察桌宠变为 WAITING，再点击“拒绝但继续”。</p>
<button id="decline" disabled>拒绝但继续（decline）</button><button id="cancel" disabled>取消并中断（cancel）</button>
<pre id="proof"></pre><pre id="reply"></pre><small>只影响这一轮验收，不更改权限策略、不保存放行规则。关闭服务可在启动终端按 Ctrl+C。</small>
<script>
let current=null;
async function poll(){try{current=await(await fetch(location.pathname+'/state')).json();
document.getElementById('phase').textContent=current.error||current.phase;
document.getElementById('command').textContent=current.command||'等待真实审批请求…';
document.getElementById('decline').disabled=!current.canDecline;
document.getElementById('cancel').disabled=!current.canCancel;
document.getElementById('proof').textContent=JSON.stringify({真实Hook等待:current.hookWaiting,桌宠任务:current.petTaskState,已捕获等待:current.sawWaiting,人工决定:current.decisionSent,请求已解除:current.requestResolved,命令结果:current.commandStatus,本轮结果:current.turnStatus},null,2);
document.getElementById('reply').textContent=current.reply;
}catch(e){document.getElementById('phase').textContent='验收服务连接已断开';
document.getElementById('decline').disabled=true;document.getElementById('cancel').disabled=true;}}
for(let action of ['decline','cancel'])document.getElementById(action).onclick=async()=>{
if(!current||current.requestId===null)return;
let r=await fetch(location.pathname+'/decision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({requestId:current.requestId,decision:action})});
if(!r.ok)alert('请求已变化或操作不可用，请重新查看页面');await poll();};
poll();setInterval(poll,1000);
</script>'''


def main():
    client=Client();token=secrets.token_urlsafe(24)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,body,content_type='application/json'):
            data=body.encode();self.send_response(status)
            self.send_header('Content-Type',content_type+'; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.end_headers();self.wfile.write(data)
        def do_GET(self):
            if self.headers.get('Host')!=f'127.0.0.1:{server.server_port}':return self.reply(403,'{}')
            if self.path=='/'+token:return self.reply(200,PAGE,'text/html')
            if self.path=='/'+token+'/state':return self.reply(200,json.dumps(client.view(),ensure_ascii=False))
            self.reply(404,'{}')
        def do_POST(self):
            if (self.path!='/'+token+'/decision' or self.headers.get('Host')!=f'127.0.0.1:{server.server_port}' or
                    self.headers.get('Origin')!=f'http://127.0.0.1:{server.server_port}'):
                return self.reply(403,'{}')
            try:
                self.connection.settimeout(3)
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=4096:raise ValueError('Invalid body')
                body=json.loads(self.rfile.read(length))
                client.gate.decide(body['requestId'],body['decision'])
                self.reply(200,'{}')
            except (ValueError,KeyError,OSError,TypeError):self.reply(409,'{}')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    url=f'http://127.0.0.1:{server.server_port}/{token}'
    data=Path.home()/'Library/Application Support/Codex BigFish'
    (data/'manual-decline-endpoint.json').write_text(json.dumps({'url':url,'pid':os.getpid()}))
    (data/'manual-decline-endpoint.json').chmod(0o600)
    print(url,flush=True)
    threading.Thread(target=client.start_test,daemon=True).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.server_close();client.close()
        endpoint=data/'manual-decline-endpoint.json'
        try:
            if json.loads(endpoint.read_text())['pid']==os.getpid():endpoint.unlink()
        except (OSError,ValueError,KeyError):pass


if __name__=='__main__':main()
