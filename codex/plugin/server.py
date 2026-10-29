"""Local MCP App entrypoints. Read/write only the installed companion's bounded API."""
import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parent
RESOURCES = Path.home() / 'Applications/大肥鱼 · Codex.app/Contents/Resources'
DATA = Path.home() / 'Library/Application Support/Codex BigFish'
UI_URI = 'ui://codex-bigfish/companion'
VERSION = '0.4.0'
SETTINGS_CAPABILITY = {'readTool':'settings_read','updateTool':'settings_update'}
SETTINGS_FIELDS = {
    'enabled':{'type':'boolean','title':'启用大肥鱼'},
    'scalePercent':{'type':'integer','title':'角色大小（%）','minimum':1,'maximum':100,
                    'description':'1%–100%，步进 1%。气泡大小在完整设置中独立调整。'}
}


def settings_values(config):
    return {'enabled':config['enabled'],'scalePercent':round(config['scale']*100)}


def settings_patch(values):
    if not isinstance(values,dict) or not values or set(values)-SETTINGS_FIELDS.keys():
        raise ValueError('invalid settings')
    patch = {}
    if 'enabled' in values:
        if type(values['enabled']) is not bool:
            raise ValueError('invalid enabled')
        patch['enabled']=values['enabled']
    if 'scalePercent' in values:
        percent=values['scalePercent']
        if type(percent) is not int or not 1<=percent<=100:
            raise ValueError('invalid scale')
        patch['scale']=percent/100
    return patch


def tool_definitions():
    def tool(name, title, properties=None, write=False):
        return {'name':name,'title':title,'description':title,
                'inputSchema':{'type':'object','properties':properties or {},'additionalProperties':False},
                'annotations':{'readOnlyHint':not write,'destructiveHint':False,'openWorldHint':False},
                '_meta':{'ui':{'visibility':['app']}}}
    entry = tool('open_bigfish', '打开完整设置')
    entry['_meta'] = {'ui':{'resourceUri':UI_URI},'openai/ui':{'entrypoints':[{'type':'global'},{'type':'thread'}]}}
    read = tool('settings_read','读取大肥鱼插件设置')
    read['outputSchema'] = {'type':'object','properties':{
        'schema':{'type':'object'},'values':{'type':'object'},
        'layout':{'type':'array','items':{'type':'object'}}},'required':['schema','values']}
    update = tool('settings_update','保存大肥鱼插件设置',{'set':{
        'type':'object','properties':SETTINGS_FIELDS,'minProperties':1,'additionalProperties':False}},write=True)
    update['inputSchema']['required']=['set']
    update['outputSchema']={'type':'object','properties':{'values':{'type':'object'}},'required':['values']}
    return [entry, read, update,
            tool('get_config','读取大肥鱼设置'),
            tool('set_config','修改大肥鱼设置',{'patch':{'type':'object'}},write=True),
            tool('get_status','读取任务状态',{'after':{'type':'integer','minimum':0}}),
            tool('get_usage','读取 Codex 额度',{'force':{'type':'boolean'}}),
            tool('get_manifest','读取原版动画清单'),
            tool('get_frames','读取原版动画帧',{'clip':{'type':'string'},'offset':{'type':'integer','minimum':0},'count':{'type':'integer','minimum':1,'maximum':64}})]


def companion_request(path, method='GET', body=None):
    endpoint = json.loads((DATA/'endpoint.json').read_text())
    url = urllib.parse.urlsplit(endpoint['url'])
    if url.scheme!='http' or url.hostname!='127.0.0.1' or url.username or url.password or not url.port or url.path:
        raise ValueError('invalid companion endpoint')
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(endpoint['url']+path,data=data,method=method,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as response:
        return json.load(response)


def frame_batch(clip, offset, count):
    if not isinstance(clip,str) or type(offset) is not int or type(count) is not int or offset<0 or not 1<=count<=64:
        raise ValueError('invalid frame batch')
    manifest = json.loads((RESOURCES/'assets/pet-manifest.json').read_text())
    if clip not in manifest['clips']:
        raise ValueError('unknown clip')
    files = manifest['clips'][clip]['frames']
    frames = {}
    root = (RESOURCES/'assets/pet').resolve()
    for name in files[offset:offset+count]:
        path = (root/name).resolve()
        if not path.is_relative_to(root):
            raise ValueError('invalid frame path')
        frames[name] = 'data:image/webp;base64,'+base64.b64encode(path.read_bytes()).decode()
    return {'frames':frames,'total':len(files)}


def app_html():
    # Import only the installed shared UI adapter; development tests use the source copy.
    sys.path.insert(0,str(RESOURCES/'codex'))
    from client_bundle import client_source
    ui_root = RESOURCES/'codex/ui'
    page = (ui_root/'index.html').read_text()
    sdk = (BASE/'vendor/app-sdk.js').read_text()
    export_pos = sdk.rfind('export{')
    match = re.search(r'([\w$]+) as App(?:[,}])',sdk[export_pos:])
    if export_pos<0 or match is None or re.search(r'^import\s',sdk,re.M):
        raise ValueError('unexpected bundled SDK format')
    sdk = '(function(){'+sdk[:export_pos]+';window.BigFishApp='+match[1]+';})();'
    client = client_source(RESOURCES,ui_root).replace("FRAME_ENDPOINT + '?frame=' + encodeURIComponent(frame)",
                                                "window.bigfishFrames[frame] || ''")
    scripts = [
        (RESOURCES/'codex/vendor/react.production.min.js').read_text(),
        (RESOURCES/'codex/vendor/react-dom.production.min.js').read_text(),
        sdk, (BASE/'app.js').read_text(), (ui_root/'wrapper.js').read_text(), client]
    page = re.sub(r'<script\b[^>]*>\s*</script>','',page)
    inline = ''.join('<script>'+s.replace('</script','<\\/script')+'</script>' for s in scripts)
    return page.replace('</body>',inline+'</body>')


def dispatch(method, params):
    if not isinstance(params,dict):
        raise ValueError('invalid params')
    if method=='initialize':
        return {'protocolVersion':'2025-11-25','capabilities':{'tools':{},'resources':{},
                 'experimental':{'openai/settings':SETTINGS_CAPABILITY}},
                'serverInfo':{'name':'codex-bigfish','version':VERSION}}
    if method=='ping':
        return {}
    if method=='tools/list':
        return {'tools':tool_definitions()}
    if method=='resources/list':
        return {'resources':[{'uri':UI_URI,'name':'大肥鱼','mimeType':'text/html;profile=mcp-app'}]}
    if method=='resources/read':
        if params.get('uri')!=UI_URI:
            raise ValueError('unknown resource')
        return {'contents':[{'uri':UI_URI,'mimeType':'text/html;profile=mcp-app','text':app_html(),
                             '_meta':{'ui':{'csp':{'connectDomains':[],'resourceDomains':[]}},
                                      'openai/ui':{'availableDisplayModes':['fullscreen'],'preferredDisplayMode':'fullscreen'}}}]}
    if method=='tools/call':
        name, args = params.get('name'), params.get('arguments',{})
        if not isinstance(args,dict):
            raise ValueError('invalid arguments')
        base='/plugins/dsh-dafeiyu/'
        if name=='open_bigfish':
            value={'ready':True}
        elif name=='settings_read':
            value={'schema':{'type':'object','properties':SETTINGS_FIELDS},
                   'values':settings_values(companion_request(base+'config')),
                   'layout':[{'kind':'group','title':'大肥鱼设置','items':[
                       {'kind':'property','property':'enabled'},
                       {'kind':'property','property':'scalePercent'},
                       {'kind':'tool','tool':'open_bigfish'}]}]}
        elif name=='settings_update':
            value={'values':settings_values(companion_request(base+'config','PATCH',settings_patch(args.get('set'))))}
        elif name=='get_config':
            value=companion_request(base+'config')
        elif name=='set_config':
            value=companion_request(base+'config','PATCH',args.get('patch'))
        elif name=='get_status':
            after=args.get('after')
            if after is not None and (type(after) is not int or after<0):
                raise ValueError('invalid cursor')
            value=companion_request('/snapshot'+('' if after is None else '?after='+str(after)))
        elif name=='get_usage':
            value=companion_request(base+'balance','POST' if args.get('force') is True else 'GET')
        elif name=='get_manifest':
            value=json.loads((RESOURCES/'assets/pet-manifest.json').read_text())
        elif name=='get_frames':
            value=frame_batch(args.get('clip'),args.get('offset',0),args.get('count',64))
        else:
            raise ValueError('unknown tool')
        return {'content':[],'structuredContent':value}
    raise ValueError('unknown method')


def main():
    for line in sys.stdin:
        try:
            request=json.loads(line)
            if not isinstance(request,dict):
                continue
            if 'id' not in request:
                continue
            try:
                result=dispatch(request.get('method'),request.get('params') or {})
                reply={'jsonrpc':'2.0','id':request['id'],'result':result}
            except (ValueError,TypeError,KeyError,OSError):
                reply={'jsonrpc':'2.0','id':request['id'],'error':{'code':-32602,'message':'大肥鱼暂未连接或参数无效，请确认桌面伴侣正在运行。'}}
            print(json.dumps(reply,ensure_ascii=False),flush=True)
        except (ValueError,UnicodeError):
            continue


if __name__=='__main__':
    main()
