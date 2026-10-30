/* The official MCP Apps bridge carries all data; no localhost iframe/network access. */
const app = new window.BigFishApp({name:'Codex BigFish',version:'0.6.0'}, {availableDisplayModes:['fullscreen']});
const ready = app.connect();
window.bigfishFrames = Object.create(null);
let manifestPromise;
let packGeneration=0;
let animationEnabled=false;
const loadedClips = new Map();
async function rpc(name,args={}) {
  await ready;
  const result = await app.callServerTool({name,arguments:args});
  if (result.isError || !result.structuredContent) throw new Error(result.content?.find(item=>item.type==='text')?.text || 'Companion unavailable');
  return result.structuredContent;
}
function clearPackCache() {
  packGeneration++;manifestPromise=undefined;loadedClips.clear();window.bigfishFrames=Object.create(null);
}
async function packs(method,body) {
  if(method==='GET')return rpc('get_packs');
  const request=JSON.parse(body);
  const result=await rpc(request.action==='select'?'select_pack':'import_pack',request.action==='select'?{id:request.id}:{path:request.path});
  if(request.action==='select')clearPackCache();
  return result;
}
async function loadClip(name) {
  if (loadedClips.has(name)) return loadedClips.get(name);
  const generation=packGeneration;
  const promise = (async()=>{
    let offset=0,total=1;
    while(offset<total) {
      const result=await rpc('get_frames',{clip:name,offset,count:64});
      if(generation!==packGeneration)throw new Error('角色包已切换，请重试');
      Object.assign(window.bigfishFrames,result.frames);total=result.total;offset+=64;
    }
  })();
  loadedClips.set(name,promise);
  try { await promise; } catch(e) { loadedClips.delete(name);throw e; }
}
async function manifest() {
  animationEnabled=true;
  if (!manifestPromise) manifestPromise=rpc('get_manifest')
    .then(async value=>{await loadClip(value.clips.idle?'idle':value.stateMap?.IDLE||Object.keys(value.clips)[0]);return value;})
    .catch(error=>{manifestPromise=undefined;throw error;});
  return manifestPromise;
}
window.fetch = async (input,options={}) => {
  const path=String(input).split('?')[0];
  const method=options.method||'GET';
  const routes={
    '/plugins/dsh-dafeiyu/config':()=>method==='PATCH'?rpc('set_config',{patch:JSON.parse(options.body)}):rpc('get_config'),
    '/plugins/dsh-dafeiyu/balance':()=>rpc('get_usage',{force:method==='POST'}),
    '/plugins/dsh-dafeiyu/manifest':()=>manifest(),
    '/plugins/dsh-dafeiyu/packs':()=>packs(method,options.body),
    '/plugins/dsh-dafeiyu/play':()=>rpc('play_clip',JSON.parse(options.body))
  };
  try {
    if (!routes[path]) throw new Error('Unknown companion endpoint');
    const value=await routes[path]();
    return new Response(JSON.stringify(value),{status:200,headers:{'Content-Type':'application/json'}});
  } catch (error) {
    return new Response(JSON.stringify({error:error.message||'大肥鱼暂未连接，请启动桌面伴侣。'}),{status:503});
  }
};
const streams=new Set();
let polling=false;
async function poll() {
  if(polling||!streams.size)return;
  polling=true;
  try {
    for(const stream of streams) {
      const snapshot=await rpc('get_status',stream.cursor==null?{}:{after:stream.cursor});
      for(const message of snapshot.messages) {
      if(message.kind==='pack')clearPackCache();
      if(animationEnabled&&(message.kind==='state'||message.kind==='pulse')) {
        const m=await manifest();
        const clip=message.state==='WORKING'&&m.workingActivityMap?.[message.activity]||m.stateMap[message.state]||'idle';
        await loadClip(clip);
      }
        stream.onmessage?.({data:JSON.stringify(message)});
      }
      stream.cursor=snapshot.cursor;
    }
  } catch {
    for(const stream of streams)stream.onerror?.({});
  } finally {polling=false;}
}
setInterval(poll,750);
window.EventSource=class {
  constructor(){streams.add(this);void poll();}
  close(){streams.delete(this);}
};
app.onhostcontextchanged=(context)=>{
  const insets=context.safeAreaInsets;
  if(insets)document.body.style.padding=`${insets.top||0}px ${insets.right||0}px ${insets.bottom||0}px ${insets.left||0}px`;
};
