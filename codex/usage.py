"""Codex quota reads through the documented app-server RPC. Never starts a turn."""
import json
import math
import os
import re
import selectors
import signal
import subprocess
import time
from pathlib import Path

CLI_CANDIDATES = (
    '/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex',
    '/Applications/Codex.app/Contents/Resources/codex',
)


def window_label(minutes):
    if isinstance(minutes, (int, float)) and not isinstance(minutes, bool) and minutes > 0:
        if minutes % 1440 == 0:
            return f'{minutes / 1440:g} 天额度'
        if minutes % 60 == 0:
            return f'{minutes / 60:g} 小时额度'
        return f'{minutes:g} 分钟额度'
    return '额度窗口'


def parse_usage(result):
    if not isinstance(result, dict):
        raise ValueError('invalid quota response')
    buckets = result.get('rateLimitsByLimitId') or {'codex': result.get('rateLimits')}
    if not isinstance(buckets, dict):
        raise ValueError('invalid quota buckets')
    windows, plan, credits = [], None, None
    for limit_id, bucket in list(buckets.items())[:30]:
        if not isinstance(bucket, dict):
            continue
        bucket_plan = bucket.get('planType', bucket.get('plan_type'))
        if isinstance(bucket_plan, str):
            plan = bucket_plan[:40]
        credit = bucket.get('credits')
        if isinstance(credit, dict):
            balance = credit.get('balance')
            if isinstance(balance, str) and re.fullmatch(r'\d{1,20}(?:\.\d{1,20})?', balance):
                credits = balance
        for slot in ('primary', 'secondary'):
            window = bucket.get(slot)
            if not isinstance(window, dict):
                continue
            used = window.get('usedPercent', window.get('used_percent'))
            if type(used) not in (int, float) or not math.isfinite(used):
                continue
            used = min(100, max(0, used))
            reset = window.get('resetsAt', window.get('resets_at'))
            reset = reset if type(reset) in (int, float) and math.isfinite(reset) and reset > 0 else None
            minutes = window.get('windowDurationMins', window.get('window_minutes'))
            minutes = minutes if type(minutes) in (int, float) and math.isfinite(minutes) else None
            windows.append(dict(id=str(limit_id)[:80] + ':' + slot, limitId=str(limit_id)[:80],
                                label=window_label(minutes), usedPercent=used, remainingPercent=100-used,
                                windowDurationMins=minutes, resetsAt=reset))
    return dict(status='ready', provider='codex', windows=windows, planType=plan, creditsBalance=credits,
                checkedAt=int(time.time()*1000))


def usage_summary(snapshot, now=None):
    windows = snapshot.get('windows') or []
    if not windows:
        return 'Codex · 暂未提供额度数据'
    now = time.time() if now is None else now
    summaries = []
    for window in windows[:2]:
        label = window['label']
        reset = window.get('resetsAt')
        if reset is not None:
            seconds = reset - now
            if seconds <= 0:
                summaries.append('Codex · 等待额度刷新')
                continue
            hours = int(seconds // 3600)
            if hours:
                days, hours = divmod(hours, 24)
                label = f'{days} 天 {hours} 小时额度'
            else:
                label = '不足 1 小时额度'
        summaries.append('Codex · ' + label + f"剩余 {window['remainingPercent']:g}%")
    return ' · '.join(summaries)


class UsageRPC:
    """One isolated read-only stdio connection; no credential files are read by us."""
    ALLOWED = {'initialize', 'initialized', 'account/rateLimits/read'}

    def __init__(self, timeout=15, proxy_socket=None):
        cli = next((p for p in CLI_CANDIDATES if Path(p).is_file()), None)
        if cli is None:
            raise OSError('Codex app-server is unavailable')
        command = [cli, 'app-server', '--listen', 'stdio://'] if proxy_socket is None else [cli,'app-server','proxy','--sock',str(proxy_socket)]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
                                        start_new_session=True)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.pending = b''
        self.sequence = 0
        self.timeout = timeout

    def __call__(self, method, params=None):
        if method not in self.ALLOWED:
            raise ValueError('RPC method is not permitted')
        self.sequence += 1
        seq = self.sequence
        value = {'method': method}
        if method != 'initialized':
            value['id'] = seq
        if params is not None:
            value['params'] = params
        self.process.stdin.write((json.dumps(value)+'\n').encode())
        self.process.stdin.flush()
        if method == 'initialized':
            return {}
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            while b'\n' in self.pending:
                line, self.pending = self.pending.split(b'\n', 1)
                response = json.loads(line)
                if response.get('id') == seq:
                    if 'error' in response:
                        raise OSError('Codex quota API returned an error')
                    return response.get('result', {})
            for key, _ in self.selector.select(timeout=0.2):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    raise OSError('Codex quota connection closed')
                self.pending += chunk
                if len(self.pending) > 8*1024*1024:
                    raise ValueError('Codex RPC response too large')
        raise TimeoutError('Codex quota read timed out')

    def close(self):
        self.selector.close()
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
            self.process.wait(timeout=3)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait()
        for stream in (self.process.stdin, self.process.stdout):
            stream.close()


def read_usage(rpc=None):
    owned = rpc is None
    rpc = UsageRPC() if owned else rpc
    try:
        rpc('initialize', {'clientInfo': {'name': 'codex_bigfish', 'title': 'Codex BigFish', 'version': '0.2.0'}})
        rpc('initialized', {})
        result = parse_usage(rpc('account/rateLimits/read'))
        result['source'] = 'account'
        return result
    finally:
        if owned:
            rpc.close()
