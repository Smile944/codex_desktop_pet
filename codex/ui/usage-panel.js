  function BalancePanel({ enabled, source }) {
    const [snapshot, setSnapshot] = useState(null)
    const [busy, setBusy] = useState(false)
    const sequence = useRef(0)
    const request = async (force = false) => {
      const seq = ++sequence.current
      setBusy(true)
      try {
        const response = await fetch(BALANCE_ENDPOINT, { method: force ? 'POST' : 'GET', cache: 'no-store' })
        if (!response.ok) throw new Error('usage')
        const next = await response.json()
        if (seq === sequence.current) setSnapshot(next)
      } catch {
        if (seq === sequence.current) setSnapshot({status:'error',error:'暂时无法读取 Codex 额度，请稍后刷新。'})
      } finally { if (seq === sequence.current) setBusy(false) }
    }
    useEffect(() => {
      setSnapshot(null)
      if (!enabled) return
      void request()
      const timer = setInterval(() => void request(), 60000)
      const stream = new EventSource(EVENTS_ENDPOINT)
      stream.onmessage = (event) => {
        try {
          const next = JSON.parse(event.data)
          if (next.kind === 'balance') {
            sequence.current += 1; setSnapshot(next); setBusy(false)
          }
        } catch {}
      }
      return () => { clearInterval(timer); stream.close(); sequence.current += 1 }
    }, [enabled, source])
    if (!enabled) return null
    const percent = (value) => new Intl.NumberFormat('zh-CN', {maximumFractionDigits:1}).format(value) + '%'
    const reset = (value) => value ? new Date(value*1000).toLocaleString('zh-CN') : '暂未提供'
    return React.createElement('section', {'aria-label':'Codex 额度','data-testid':'codex-usage',style:{borderTop:'1px solid var(--border-color, #d8d8d8)',paddingTop:14}},
      React.createElement('div', {style:rowStyle},
        React.createElement('strong', null, 'Codex 额度'),
        React.createElement('button',{type:'button',disabled:busy,onClick:()=>void request(true)},busy?'查询中…':'刷新额度')),
      snapshot?.source ? React.createElement('small',null,snapshot.source==='session'?'本地会话记录 · 可能有更新延迟':'当前登录的 Codex 账户') : null,
      snapshot?.windows?.length ? React.createElement('table',{style:{width:'100%',textAlign:'left',marginTop:10}},
        React.createElement('thead',null,React.createElement('tr',null,...['额度窗口','已用','剩余','重置时间'].map(x=>React.createElement('th',{key:x,scope:'col'},x)))),
        React.createElement('tbody',null,...snapshot.windows.map(row=>React.createElement('tr',{key:row.id},
          React.createElement('th',{scope:'row'},row.label),
          React.createElement('td',null,percent(row.usedPercent)),
          React.createElement('td',null,percent(row.remainingPercent)),
          React.createElement('td',null,reset(row.resetsAt)))))) : null,
      snapshot?.planType ? React.createElement('p',null,'订阅：'+snapshot.planType.toUpperCase()) : null,
      snapshot?.creditsBalance != null ? React.createElement('p',null,'额度点数：'+new Intl.NumberFormat('zh-CN',{maximumFractionDigits:2}).format(snapshot.creditsBalance)) : null,
      snapshot?.error ? React.createElement('p',{role:'status'},snapshot.error) : null,
      snapshot?.status==='ready' && !snapshot.windows?.length ? React.createElement('p',{role:'status'},'当前接口暂未提供额度窗口。') : null,
      snapshot?.checkedAt ? React.createElement('small',null,'更新时间：'+new Date(snapshot.checkedAt).toLocaleTimeString()+' · 每分钟自动刷新') : null)
  }
