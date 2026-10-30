  function animationGroups(manifest) {
    const animations = manifest.animations || {}
    const library = new Set(Array.isArray(manifest.libraryClips) ? manifest.libraryClips : Object.keys(manifest.clips || {}))
    const seen = new Set()
    const groups = []
    const add = (id, label, candidates) => {
      const clips = (Array.isArray(candidates) ? candidates.flat(Infinity) : [])
        .filter(name => typeof name === 'string' && library.has(name) && manifest.clips?.[name] && !seen.has(name) && seen.add(name))
      if (clips.length) groups.push({id, label, clips})
    }
    add('idle', '待机', animations.idle)
    add('turn', '转身', animations.turn)
    add('drag', '拖动', animations.drag)
    add('clicks', '点击', animations.clicks)
    const moves = animations.moves?.actions
    add('moves', '移动', Array.isArray(moves) ? moves.map(item => item?.name) : [])
    for (const category of Array.isArray(animations.categories) ? animations.categories : []) {
      if (category && typeof category.id === 'string') add(category.id, category.id, category.actions)
    }
    add('balance', '额度事件', animations.events?.balance)
    add('whisper', '碎碎念', animations.events?.whisper)
    add('workStatus', '工作状态', animations.events?.workStatus)
    add('other', '其他动作', [...library])
    return groups
  }

  function animationEntries(manifest, query, category) {
    const groups = animationGroups(manifest)
    const ids = category === 'all' ? groups.flatMap(group => group.clips) : (groups.find(group => group.id === category)?.clips || [])
    const needle = query.trim().toLocaleLowerCase()
    return ids.map(id => ({id, label: manifest.clipLabels?.[id] || id}))
      .filter(item => !needle || (item.id + ' ' + item.label).toLocaleLowerCase().includes(needle))
  }

  function AnimationPanel({ value, writable, write }) {
    const [library, setLibrary] = useState(null)
    const [query, setQuery] = useState('')
    const [category, setCategory] = useState('all')
    const [path, setPath] = useState('')
    const [busy, setBusy] = useState(false)
    const [notice, setNotice] = useState('')
    const pending = useRef(false)
    const endpoint = '/plugins/dsh-dafeiyu/packs'
    const read = async () => {
      const response = await fetch(endpoint, {cache:'no-store'})
      const result = await response.json()
      if (!response.ok) throw new Error(result.error || '无法读取动画库')
      setLibrary(result)
      return result
    }
    useEffect(() => { void read().catch(error => setNotice(error.message)) }, [])
    const action = async (url, body) => {
      if (pending.current) return
      pending.current = true; setBusy(true); setNotice(body.action === 'import' ? '正在转换动画，可能需要数分钟，请等待；连接中断后请刷新列表确认，请勿重复导入。' : '')
      try {
        const response = await fetch(url, {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify(body)})
        const result = await response.json()
        if (!response.ok) throw new Error(result.error || '操作失败')
        if (url === endpoint) {setLibrary(result);setCategory('all')}
        setNotice(body.action === 'import' ? '导入完成，请在角色包中选择。' : body.clip ? '已点播，播放后恢复当前 Codex 状态。' : '已切换角色包。')
      } catch (error) {
        setNotice(body.action === 'import' ? `${error.message}。导入可能仍在进行，请刷新角色包列表确认后再操作。` : error.message)
      } finally {pending.current=false;setBusy(false)}
    }
    const groups = library ? animationGroups(library.manifest) : []
    const entries = library ? animationEntries(library.manifest, query, category) : []
    return React.createElement('section', {style:{display:'grid',gap:10},'aria-label':'动画库与角色包'},
      React.createElement('strong', null, '动画库与角色包'),
      React.createElement(Field, {label:'自动播放随机动画',hint:'保留任务状态、审批提示和点击动作。'},
        React.createElement('input', {type:'checkbox',checked:value.randomAnimations !== false,disabled:!writable || busy,onChange:event=>void write('randomAnimations',event.target.checked)})),
      library ? React.createElement(Field, {label:'角色包',hint:library.packs.length === 1 ? '当前仅有原版角色；可导入自己的本地角色包。' : '每个角色包使用自己的动画素材。'},
        React.createElement('select', {style:selectStyle,value:library.selected,disabled:!writable || busy,onChange:event=>void action(endpoint,{action:'select',id:event.target.value})},
          library.packs.map(pack=>React.createElement('option',{key:pack.id,value:pack.id},`${pack.name}（${pack.clipCount} 个动作）`)))) : null,
      React.createElement('label',null,'本地角色包路径',React.createElement('input',{type:'text',value:path,placeholder:'/Users/…/角色.zip 或 pet/角色-config.json',disabled:busy,onChange:event=>setPath(event.target.value),style:{width:'100%',boxSizing:'border-box'}})),
      React.createElement('small',null,'支持 ZIP、本地上游 pet 配置文件或包目录；导入会转换视频，可能需要数分钟，原始文件保持不变。'),
      React.createElement('div',null,
        React.createElement('button',{disabled:!writable || busy || !path.trim(),onClick:()=>void action(endpoint,{action:'import',path:path.trim()})},busy?'处理中…':'导入本地角色包'),
        React.createElement('button',{disabled:busy,onClick:()=>void read().then(()=>setNotice('角色包列表已刷新。')).catch(error=>setNotice(error.message))},'刷新列表')),
      React.createElement('label',null,'搜索动作',React.createElement('input',{type:'search',value:query,onChange:event=>setQuery(event.target.value),placeholder:'中文名称或动作 ID'})),
      React.createElement('label',null,'分类 ',React.createElement('select',{value:category,onChange:event=>setCategory(event.target.value)},
        React.createElement('option',{value:'all'},'全部动作'),
        groups.map(group=>React.createElement('option',{key:group.id,value:group.id},group.label)))),
      React.createElement('small',null,`${entries.length} 个动作；点播一次后恢复任务状态，审批和拖动优先。`),
      React.createElement('div',{style:{display:'flex',gap:6,flexWrap:'wrap',maxHeight:250,overflowY:'auto'}},
        entries.map(item=>React.createElement('button',{key:item.id,title:item.id,disabled:!writable || busy,onClick:()=>void action('/plugins/dsh-dafeiyu/play',{clip:item.id})},item.label))),
      notice ? React.createElement('p',{role:'status',style:{margin:0,overflowWrap:'anywhere'}},notice) : null)
  }

