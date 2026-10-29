import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from install_plugin import prepare_package


class PackageTests(unittest.TestCase):
    def test_contained_launcher_is_valid_and_preserves_portable_source(self):
        source=Path(__file__).parent/'plugin'
        before=(source/'mcp.json').read_bytes()
        with tempfile.TemporaryDirectory(prefix='bigfish package ') as tmp:
            package=Path(tmp)/'plugin with spaces'
            prepare_package(source,package,sys.executable)
            server=json.loads((package/'mcp.json').read_text())['mcpServers']['bigfish']
            self.assertTrue(server['command'].startswith('./'),'Codex rejects an absolute executable path')
            launcher=package/server['command']
            self.assertTrue(launcher.is_file() and os.access(launcher,os.X_OK))
            request=json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})+'\n'
            result=subprocess.run([server['command'],*server['args']],cwd=package,
                                  input=request,text=True,capture_output=True,check=True,timeout=5)
            capability=json.loads(result.stdout)['result']['capabilities']['experimental']['openai/settings']
            self.assertEqual(capability['readTool'],'settings_read')
        self.assertEqual((source/'mcp.json').read_bytes(),before)


if __name__=='__main__':unittest.main()
