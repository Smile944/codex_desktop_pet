import http.client
import io
from contextlib import redirect_stdout
from types import SimpleNamespace
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from host import ConfigStore, Host
import build
from test_plugin import plugin

ROOT = Path(__file__).resolve().parents[1]
BASE = '/plugins/dsh-dafeiyu/'


class AnimationSettingsTests(unittest.TestCase):
    def test_build_embeds_converter_and_licenses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);resources=root/'Resources';resources.mkdir()
            binary=root/'ffmpeg';binary.write_bytes(b'pinned-media');binary.chmod(0o755)
            with patch.object(build,'ensure_media',return_value=binary):
                build.bundle_media(resources,'arm64')
            self.assertEqual((resources/'media/ffmpeg').read_bytes(),b'pinned-media')
            self.assertTrue((resources/'media/ffmpeg').stat().st_mode & 0o111)
            self.assertTrue((resources/'codex/media-lock.json').is_file())
            self.assertTrue(any((resources/'media/licenses').iterdir()))

    def test_animation_preferences_preserve_existing_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'settings.json'
            path.write_text(json.dumps({'soundEnabled':False,'scale':0.4}))
            store = ConfigStore(path)
            self.assertTrue(store.value['randomAnimations'])
            self.assertEqual(store.value['petPack'],'builtin')
            store.update({'randomAnimations':False,'petPack':'cat'})
            self.assertFalse(ConfigStore(path).value['randomAnimations'])
            self.assertFalse(ConfigStore(path).value['soundEnabled'])
            for value in ('../cat','',True):
                with self.assertRaises(ValueError):store.update({'petPack':value})

    def test_host_switch_updates_manifest_frames_and_restart_without_replaying_play(self):
        with tempfile.TemporaryDirectory() as tmp, patch('host.DATA',Path(tmp)):
            host = Host(ROOT,'/nonexistent')
            assets = Path(tmp)/'cat'; (assets/'pet').mkdir(parents=True)
            (assets/'pet/a.webp').write_bytes(b'cat-frame')
            manifest = {'clips':{'猫':{'frames':['a.webp']}},'animations':{'idle':['猫']}}
            (assets/'pet-manifest.json').write_text(json.dumps(manifest))
            class Packs:
                def list(self):return [{'id':'builtin','name':'大肥鱼','clipCount':16},{'id':'cat','name':'猫','clipCount':1}]
                def resolve(self,name):
                    if name=='cat':return assets
                    if name=='builtin':return ROOT/'assets'
                    raise ValueError('unknown pack')
                def import_pack(self,path):raise ValueError('invalid media')
            host.pack_store = Packs()
            worker = threading.Thread(target=host.server.serve_forever,daemon=True);worker.start()
            client = http.client.HTTPConnection('127.0.0.1',host.port,timeout=3)
            def request(path,body=None):
                client.close()
                client.request('GET' if body is None else 'POST',BASE+path,None if body is None else json.dumps(body),{'Content-Type':'application/json'})
                result=client.getresponse();return result.status,result.read()
            try:
                with patch.object(host,'stop_helper',side_effect=lambda:setattr(host,'process',None)) as stop, patch.object(host,'start_helper') as start:
                    host.process = object()
                    status,body=request('packs',{'action':'select','id':'cat'})
                    self.assertEqual(status,200,body)
                    self.assertEqual(json.loads(body)['selected'],'cat')
                    stop.assert_called_once();start.assert_called_once()
                host.process=None
                self.assertEqual(host.assets,assets)
                self.assertEqual(host.frames,{'a.webp'})
                self.assertEqual(request('frame?frame=a.webp'),(200,b'cat-frame'))
                self.assertEqual(request('play',{'clip':'unknown'})[0],400)
                host.process=SimpleNamespace(poll=lambda:None,stdin=io.StringIO())
                self.assertEqual(request('play',{'clip':'猫'})[0],200)
                self.assertEqual(host.recent_events[-1][1]['kind'],'play')
                self.assertNotIn('play',host.latest)
                status,body=request('packs',{'action':'import','path':'/bad.zip'})
                self.assertEqual(status,400)
                self.assertEqual(host.store.value['petPack'],'cat')
                self.assertEqual(request('packs',{'action':'select','id':'missing'})[0],400)
                self.assertEqual(host.store.value['petPack'],'cat')
            finally:
                client.close();host.server.shutdown();host.server.server_close()

    def test_helper_restart_restores_complete_current_quota(self):
        with tempfile.TemporaryDirectory() as tmp, patch('host.DATA',Path(tmp)):
            host=Host(ROOT,'/nonexistent')
            process=SimpleNamespace(poll=lambda:None,stdin=io.StringIO(),stdout=io.StringIO(),stderr=io.StringIO())
            host.balance={'status':'ready','provider':'codex','windows':[{'usedPercent':85,'remainingPercent':15,'label':'5h'}]}
            try:
                with patch('host.subprocess.Popen',return_value=process):
                    host.start_helper()
                messages=[json.loads(line) for line in process.stdin.getvalue().splitlines()]
                quota=next(message for message in messages if message['kind']=='balance')
                self.assertEqual(quota['status'],'ready')
                self.assertEqual(quota['windows'],[{'usedPercent':85,'remainingPercent':15,'label':'5h'}])
            finally:host.server.server_close()

    def test_play_requires_a_visible_running_helper_and_preserves_manual_close(self):
        with tempfile.TemporaryDirectory() as tmp, patch('host.DATA',Path(tmp)):
            host=Host(ROOT,'/nonexistent')
            host.process=SimpleNamespace(poll=lambda:None,stdin=io.StringIO())
            worker=threading.Thread(target=host.server.serve_forever,daemon=True);worker.start()
            def play():
                client=http.client.HTTPConnection('127.0.0.1',host.port,timeout=3)
                try:
                    client.request('POST',BASE+'play',json.dumps({'clip':'idle'}),{'Content-Type':'application/json'})
                    result=client.getresponse();return result.status,json.loads(result.read())
                finally:client.close()
            try:
                host.store.update({'enabled':False})
                status,body=play();self.assertEqual(status,409);self.assertIn('启用',body['error'])
                host.store.update({'enabled':True})
                host.host_pid=42;host.suppressed_pid=42
                status,body=play();self.assertEqual(status,409);self.assertIn('重新开启',body['error'])
                self.assertEqual(host.suppressed_pid,42)
                host.suppressed_pid=None
                status,body=play();self.assertEqual(status,200)
                host.process=None
                status,body=play();self.assertEqual(status,409);self.assertIn('尚未运行',body['error'])
            finally:host.server.shutdown();host.server.server_close()

    def test_mcp_manifest_and_frames_use_selected_host_api(self):
        manifest={'clips':{'猫':{'frames':['a.webp']}}}
        with patch.object(plugin,'companion_request',return_value=manifest) as request:
            value=plugin.dispatch('tools/call',{'name':'get_manifest'})['structuredContent']
            self.assertEqual(value,manifest)
            request.assert_called_once_with(BASE+'manifest')
        with patch.object(plugin,'companion_request',return_value=manifest),patch.object(plugin,'companion_bytes',return_value=b'cat') as request:
            self.assertEqual(plugin.frame_batch('猫',0,1)['total'],1)
            request.assert_called_once_with(BASE+'frame?frame=a.webp')

    def test_mcp_transport_preserves_action_errors_for_the_settings_ui(self):
        request = {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'import_pack','arguments':{'path':'/bad.zip'}}}
        output=io.StringIO()
        with patch.object(plugin.sys,'stdin',io.StringIO(json.dumps(request)+'\n')), patch.object(plugin,'dispatch',side_effect=ValueError('损坏的动画文件')), redirect_stdout(output):
            plugin.main()
        result=json.loads(output.getvalue())['result']
        self.assertTrue(result['isError'])
        self.assertEqual(result['content'][0]['text'],'损坏的动画文件')

    def test_mcp_pack_and_play_tools_forward_errors(self):
        for name,args,path,body in [('get_packs',{},'packs',None),('select_pack',{'id':'cat'},'packs',{'action':'select','id':'cat'}),('import_pack',{'path':'/cat.zip'},'packs',{'action':'import','path':'/cat.zip'}),('play_clip',{'clip':'猫'},'play',{'clip':'猫'})]:
            with self.subTest(name=name),patch.object(plugin,'companion_request',side_effect=ValueError('rejected')) as request:
                with self.assertRaisesRegex(ValueError,'rejected'):
                    plugin.dispatch('tools/call',{'name':name,'arguments':args})
                if body is None:request.assert_called_once_with(BASE+path)
                else:request.assert_called_once_with(BASE+path,'POST',body)


if __name__=='__main__':unittest.main()
