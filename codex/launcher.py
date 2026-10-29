"""Double-click opens settings; installed LaunchAgent owns the companion."""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = Path.home() / 'Library/Application Support/Codex BigFish'
DATA.mkdir(parents=True, exist_ok=True, mode=0o700)


def endpoint():
    try:
        state = json.loads((DATA / 'endpoint.json').read_text())
        url = state['url']
        if not url.startswith('http://127.0.0.1:'):
            return None
        with urllib.request.urlopen(url + '/health', timeout=1) as response:
            if json.load(response)['pid'] == state['pid']:
                return url
    except (OSError, ValueError, KeyError):
        pass
    return None


url = endpoint()
if url is None:
    resources = BASE.parent
    helper = resources / 'BigFish Helper.app/Contents/MacOS/bigfish-helper'
    with (DATA / 'host.log').open('ab') as log:
        subprocess.Popen([sys.executable, '-B', '-u', str(BASE / 'host.py'), '--resources', str(resources),
                          '--helper', str(helper)], stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         start_new_session=True)
    for _ in range(40):
        time.sleep(0.1)
        url = endpoint()
        if url:
            break
if url:
    subprocess.run(['/usr/bin/open', url], check=False)
