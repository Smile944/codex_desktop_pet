"""Smoke-test the installed local MCP package; does not drive the Codex UI."""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'codex'))
from usage import UsageRPC


class PluginInspectionRPC(UsageRPC):
    ALLOWED={'initialize','initialized','plugin/read','mcpServerStatus/list','hooks/list'}


def native_discovery(version,include_hooks=False):
    rpc=PluginInspectionRPC(timeout=20)
    try:
        rpc('initialize',{'clientInfo':{'name':'bigfish_plugin_verification','version':version},
                          'capabilities':{'experimentalApi':True}})
        rpc('initialized',{})
        marketplace=Path.home()/'Library/Application Support/Codex BigFish/plugin-marketplace/.agents/plugins/marketplace.json'
        plugin=rpc('plugin/read',{'pluginName':'codex-bigfish','marketplacePath':str(marketplace)})['plugin']
        assert plugin['summary']['localVersion']==version
        assert plugin['mcpServers']==['bigfish'], 'Codex rejected or did not discover the plugin MCP server'
        status=rpc('mcpServerStatus/list',{'limit':100})
        server=next(s for s in status['data'] if s['name']=='bigfish')
        assert server['toolsError'] is None
        assert server['serverInfo']['version']==version
        assert server['serverCapabilities']['experimental']['openai/settings']=={
            'readTool':'settings_read','updateTool':'settings_update'}
        assert {'settings_read','settings_update','open_bigfish'} <= server['tools'].keys()
        result={'serverNames':plugin['mcpServers'],'settingsCapability':True,
                'discoveredToolCount':len(server['tools']),'toolsError':server['toolsError']}
        if include_hooks:
            groups=rpc('hooks/list',{})['data']
            hooks=[h for group in groups for h in group['hooks'] if h.get('statusMessage')=='大肥鱼：仅观察审批状态']
            assert len(hooks)==8
            assert all(h['enabled'] and h['trustStatus']=='untrusted' for h in hooks)
            result.update(observerHookCount=8,untrustedObserverHookCount=8)
        return result
    finally:
        rpc.close()


def main():
    version = json.loads((ROOT/'codex/plugin/plugin.json').read_text())['version']
    package = Path.home()/f'.codex/plugins/cache/codex-bigfish-local/codex-bigfish/{version}'
    command = json.loads((package/'mcp.json').read_text())['mcpServers']['bigfish']
    requests = [
        ('initialize', {}), ('tools/list', {}),
        ('resources/read', {'uri':'ui://codex-bigfish/companion'}),
        ('tools/call', {'name':'get_config'}), ('tools/call', {'name':'get_status'}),
        ('tools/call', {'name':'get_usage'}),
        ('tools/call', {'name':'get_frames','arguments':{'clip':'idle','count':1}}),
        ('tools/call', {'name':'settings_read'})]
    data = ''.join(json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':params})+'\n'
                   for i,(method,params) in enumerate(requests,1))
    result = subprocess.run([command['command'], *[s.replace('${PLUGIN_ROOT}',str(package)) for s in command['args']]],
                            cwd=package,input=data,text=True,capture_output=True,timeout=45,check=True)
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(replies)==len(requests), 'missing response'
    assert all('result' in reply for reply in replies), 'MCP call failed'
    values = [r['result'] for r in replies]
    assert values[0]['serverInfo']['version']==version
    assert values[0]['capabilities']['experimental']['openai/settings']=={
        'readTool':'settings_read','updateTool':'settings_update'}
    html = values[2]['contents'][0]['text']
    assert '<iframe' not in html and 'src="https://' not in html
    scripts = re.findall(r'<script>(.*?)</script>',html,re.S)
    node = Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
    with tempfile.TemporaryDirectory() as tmp:
        for index,script in enumerate(scripts):
            path = Path(tmp)/f'script-{index}.js'
            path.write_text(script)
            subprocess.run([str(node),'--check',str(path)],check=True,capture_output=True)
    config, status, usage, frames = [v['structuredContent'] for v in values[3:7]]
    native=values[7]['structuredContent']
    assert native['values']=={'enabled':config['enabled'],'scalePercent':round(config['scale']*100)}
    assert native['schema']['properties']['scalePercent']['minimum']==1
    assert native['schema']['properties']['scalePercent']['maximum']==100
    assert {'kind':'tool','tool':'open_bigfish'} in native['layout'][0]['items']
    assert 0.01 <= config['scale'] <= 1
    assert type(status['cursor']) is int and isinstance(status['messages'],list)
    assert usage['provider']=='codex' and usage['status']=='ready'
    assert len(frames['frames'])==1 and all(v.startswith('data:image/webp;base64,') for v in frames['frames'].values())
    summary = {'version':version,'installedPackage':str(package),
               'methods':[m for m,_ in requests], 'toolNames':[t['name'] for t in values[1]['tools']],
               'htmlBytes':len(html.encode()),'htmlSHA256':hashlib.sha256(html.encode()).hexdigest(),
               'inlineScriptsChecked':len(scripts),'savedScale':config['scale'],
               'quotaStatus':usage['status'],'quotaWindowCount':len(usage['windows']),
               'originalFrameRoundTrip':True,'nativeSettingsRead':True,
               'nativeSettingsFields':list(native['values']),'fullSettingsAction':'open_bigfish',
               'codexNativeViewAutomated':False}
    summary['codexNativeDiscovery']=native_discovery(version)
    (ROOT/'codex/evidence/plugin-smoke.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()
