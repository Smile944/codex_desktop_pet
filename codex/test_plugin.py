import importlib.util
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('bigfish_mcp', ROOT/'plugin/server.py')
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class PluginTests(unittest.TestCase):
    def setUp(self):
        # Source tests must also work on a new Mac before any app is installed.
        resources=patch.object(plugin,'RESOURCES',ROOT.parent)
        resources.start()
        self.addCleanup(resources.stop)

    def test_host_discovers_native_plugin_settings_and_full_ui_action(self):
        capability=plugin.dispatch('initialize',{})['capabilities']['experimental']['openai/settings']
        self.assertEqual(capability,{'readTool':'settings_read','updateTool':'settings_update'})
        tools={t['name']:t for t in plugin.tool_definitions()}
        self.assertIn('outputSchema',tools['settings_read'])
        self.assertIn('outputSchema',tools['settings_update'])
        with patch.object(plugin,'companion_request',return_value={'enabled':True,'scale':0.55}):
            result=plugin.dispatch('tools/call',{'name':'settings_read'})['structuredContent']
        self.assertEqual(result['values'],{'enabled':True,'scalePercent':55})
        self.assertEqual(result['schema']['properties']['scalePercent']['minimum'],1)
        self.assertEqual(result['schema']['properties']['scalePercent']['maximum'],100)
        self.assertIn({'kind':'tool','tool':'open_bigfish'},result['layout'][0]['items'])

    def test_native_settings_write_only_changed_fields_to_existing_store(self):
        with patch.object(plugin,'companion_request',return_value={'enabled':True,'scale':0.01}) as call:
            result=plugin.dispatch('tools/call',{'name':'settings_update','arguments':{'set':{'scalePercent':1}}})
            call.assert_called_once_with('/plugins/dsh-dafeiyu/config','PATCH',{'scale':0.01})
        self.assertEqual(result['structuredContent']['values'],{'enabled':True,'scalePercent':1})
        for change in [{'scalePercent':0},{'scalePercent':101},{'scalePercent':True},
                       {'scalePercent':1.5},{'enabled':1},{'unknown':True},{}]:
            with self.subTest(change=change),patch.object(plugin,'companion_request') as call:
                with self.assertRaises(ValueError):
                    plugin.dispatch('tools/call',{'name':'settings_update','arguments':{'set':change}})
                call.assert_not_called()

    def test_static_entrypoints_and_app_only_internal_tools(self):
        tools = plugin.tool_definitions()
        entry = next(t for t in tools if t['name']=='open_bigfish')
        self.assertEqual(entry['_meta']['openai/ui']['entrypoints'], [{'type':'global'},{'type':'thread'}])
        self.assertEqual(entry['_meta']['ui']['resourceUri'], plugin.UI_URI)
        for tool in tools:
            if tool['name'] != 'open_bigfish':
                self.assertEqual(tool['_meta']['ui']['visibility'], ['app'])

    def test_ui_resource_contains_official_handshake_and_no_remote_urls(self):
        html = plugin.app_html()
        self.assertIn('new window.BigFishApp', html)
        self.assertIn('app.connect()', html)
        self.assertIn('callServerTool', html)
        self.assertNotIn('<iframe', html)
        self.assertNotIn('src="https://', html)

    def test_frame_batch_rejects_invalid_clip_and_oversized_batch(self):
        with self.assertRaises(ValueError):
            plugin.frame_batch('../private', 0, 5)
        with self.assertRaises(ValueError):
            plugin.frame_batch('idle', 0, 1000)


if __name__=='__main__':
    unittest.main()
