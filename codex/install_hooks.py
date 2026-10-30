"""Merge advisory user hooks; never write hook trust or approval policies."""
import json
import os
from pathlib import Path
import shlex
import shutil
import tempfile
import time
import re
import subprocess
from install import installed_python
from usage import CLI_CANDIDATES

EVENTS=('PermissionRequest','PostToolUse','PreModelRequest','Interrupt','Stop',
        'SessionEnd','UserPromptSubmit','SessionStart')


def hooks_supported():
    cli=next((p for p in CLI_CANDIDATES if Path(p).is_file()),None)
    if cli is None:return False
    try:
        result=subprocess.run([cli,'features','list'],check=True,capture_output=True,text=True,timeout=15)
        return re.search(r'^hooks\s+\S+\s+true\s*$',result.stdout,re.M) is not None
    except (OSError,subprocess.SubprocessError):return False


def install(home=Path.home()):
    if not hooks_supported():
        print('当前宿主未启用或不支持 Hooks，已跳过观察 Hook 配置；基础桌宠仍可使用。')
        return
    resources=home/'Applications/大肥鱼 · Codex.app/Contents/Resources'
    python=shlex.quote(installed_python(home/'Applications/大肥鱼 · Codex.app'))
    script=shlex.quote(str(resources/'codex/plugin/hooks/observe.py'))
    # Missing/uninstalled companion is a no-op, never a failed permission hook.
    command=f'if [ -x {python} ] && [ -f {script} ]; then {python} -E -s -B {script} >/dev/null 2>&1 || true; fi'
    codex_home=Path(os.environ.get('CODEX_HOME',home/'.codex'))
    target=codex_home/'hooks.json'
    data=json.loads(target.read_text()) if target.exists() else {}
    hooks=data.setdefault('hooks',{})
    for event in EVENTS:
        groups=hooks.setdefault(event,[])
        if not any(any(h.get('command')==command for h in group.get('hooks',[])) for group in groups):
            groups.append({'hooks':[{'type':'command','command':command,'timeout':2,
                                    'statusMessage':'大肥鱼：仅观察审批状态'}]})
    codex_home.mkdir(parents=True,exist_ok=True)
    if target.exists():shutil.copy2(target,target.with_name('hooks.json.backup-'+str(time.time_ns())))
    fd,tmp=tempfile.mkstemp(dir=codex_home,prefix='.bigfish-hooks-')
    with os.fdopen(fd,'w') as output:json.dump(data,output,ensure_ascii=False,indent=2)
    os.replace(tmp,target)
    print('已准备观察 Hooks；请在 Codex 中人工审查并信任：'+str(target))


if __name__=='__main__':install()
