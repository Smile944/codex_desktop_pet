"""Reuse one adapted upstream React card in browser and native MCP App surfaces."""
from scale_policy import adapt_client_scale


def client_source(resources, ui_root):
    code = adapt_client_scale((resources / 'lib/client.js').read_text())
    start = code.index('  function BalancePanel(')
    end = code.index('  function BigFishCard(', start)
    code = code[:start] + (ui_root / 'usage-panel.js').read_text() + (ui_root / 'animation-panel.js').read_text() + code[end:]
    code = code.replace("          busy ? React.createElement('small'", "          React.createElement(AnimationPanel, {value, writable, write}),\n          busy ? React.createElement('small'")
    code = code.replace("    const [src, setSrc] = useState(null)", "    const [src, setSrc] = useState(null)\n    const [packRevision, setPackRevision] = useState(0)\n    const selectedPack = useRef(null)")
    code = code.replace("                  const message = JSON.parse(event.data)", "                  const message = JSON.parse(event.data)\n                  if (message.kind === 'pack' && selectedPack.current !== message.selected) {selectedPack.current = message.selected;setSrc(null);setPackRevision(n => n + 1);return}")
    code = code.replace("    }, [])\n    if (!src)", "    }, [packRevision])\n    if (!src)")
    code = code.replace("manifest.clips[name] || manifest.clips.idle", "manifest.clips[name] || manifest.clips[manifest.stateMap?.IDLE] || Object.values(manifest.clips)[0]")
    for old, new in [
        ('DSH WebUI 或桌面端', 'Codex 桌面端'), ('DSH Host', 'Codex 伴侣'),
        ('DSH 页面', '本设置页面'), ('打开 DSH', '打开 Codex'),
        ('任务状态和余额', '任务状态和额度'), ('显示余额', '显示额度'), ('余额来源', '额度来源'),
        ('气泡显示总余额，下方可查看赠送／充值明细。', '气泡显示 Codex 剩余额度，下方可查看使用比例和重置时间。'),
        ('自动模式优先使用 API Key；账户余额和 API Key 余额可能不同。', '自动读取 Codex 账户额度；会话记录可能有更新延迟。'),
        ("}, 'API Key')", "}, '会话记录')"), ("}, '已登录账户')", "}, 'Codex 账户')")]:
        code = code.replace(old, new)
    return code
