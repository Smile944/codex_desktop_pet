"""Double-click fallback must retain the packaged runtime's isolation."""
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch


class LauncherTests(unittest.TestCase):
    def test_fallback_host_disables_python_environment_and_user_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(Path, 'home', return_value=Path(tmp)), \
                 patch.object(subprocess, 'Popen') as spawn, \
                 patch('time.sleep'):
                runpy.run_path(str(Path(__file__).parent/'launcher.py'), run_name='__main__')
            arguments = spawn.call_args.args[0]
            self.assertIn('-E', arguments)
            self.assertIn('-s', arguments)
            self.assertIn('-B', arguments)


if __name__ == '__main__':
    unittest.main()
