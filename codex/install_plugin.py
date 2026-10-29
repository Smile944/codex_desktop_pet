"""Install this local-only plugin through Codex's supported marketplace CLI."""
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from usage import CLI_CANDIDATES


def prepare_package(source, package, runtime):
    """Use a contained launcher: portable MCP disallows absolute executable paths."""
    shutil.copytree(source, package, dirs_exist_ok=True)
    mcp_path = package/'mcp.json'
    mcp = json.loads(mcp_path.read_text())
    launcher=package/'run-server'
    launcher.write_text('#!/bin/sh\nunset PYTHONHOME PYTHONPATH\nexec '+shlex.quote(runtime)+' -E -s -B "$(dirname "$0")/server.py"\n')
    launcher.chmod(0o755)
    server=mcp['mcpServers']['bigfish']
    server['command']='./run-server'
    server['args']=[]
    server.pop('cwd',None)
    mcp_path.write_text(json.dumps(mcp, ensure_ascii=False, indent=2)+'\n')
    # Remove the obsolete generated legacy file from local source updates.
    (package/'.mcp.json').unlink(missing_ok=True)


def install(source=None, runtime=None):
    cli = next((p for p in CLI_CANDIDATES if Path(p).is_file()), None)
    if cli is None:
        raise OSError('Codex CLI is unavailable')
    root = Path.home()/'Library/Application Support/Codex BigFish/plugin-marketplace'
    package = root/'plugins/codex-bigfish'
    prepare_package(source or Path(__file__).parent/'plugin', package, runtime or sys.executable)
    marketplace = root/'.agents/plugins/marketplace.json'
    marketplace.parent.mkdir(parents=True, exist_ok=True)
    marketplace.write_text(json.dumps({
        'name':'codex-bigfish-local', 'interface':{'displayName':'大肥鱼本地插件'},
        'plugins':[{'name':'codex-bigfish','source':{'source':'local','path':'./plugins/codex-bigfish'},
                    'policy':{'installation':'AVAILABLE','authentication':'ON_INSTALL'},'category':'Productivity'}]
    }, ensure_ascii=False, indent=2)+'\n')
    for args in [('marketplace','add',str(root)),('add','codex-bigfish@codex-bigfish-local')]:
        subprocess.run([cli,'plugin',*args,'--json'],check=True)


if __name__ == '__main__':
    install()
