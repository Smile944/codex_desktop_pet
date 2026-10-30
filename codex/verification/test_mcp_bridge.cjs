/* Controlled App transport tests; these do not claim Codex host/UI acceptance. */
const vm=require('node:vm');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../plugin/app.js'),'utf8');
const drain=async()=>{for(let i=0;i<10;i++)await new Promise(setImmediate);};
function harness({manifestFailures=0,frameFailures=0,frameGate=null}={}) {
  const calls=[];
  const context={Response,document:{body:{style:{}}},setInterval:callback=>{context.tick=callback;}};
  context.window=context;
  context.BigFishApp=class {
    connect(){return Promise.resolve();}
    async callServerTool({name,arguments:args}) {
      calls.push({name,args});
      if(name==='get_status')return {structuredContent:{cursor:7,messages:args.after==null?[{kind:'config',reducedMotion:true},{kind:'state',state:'WORKING',activity:'search'}]:[]}};
      if(name==='get_manifest') {
        if(manifestFailures-->0)throw Error('temporary manifest failure');
        return {structuredContent:{clips:{idle:{},search:{}},stateMap:{WORKING:'search'},workingActivityMap:{search:'search'}}};
      }
      if(name==='get_frames') {
        if(frameGate)await frameGate;
        if(args.clip==='search'&&frameFailures-->0)throw Error('temporary frame failure');
        return {structuredContent:{frames:{[args.clip]:'data:image/webp;base64,AA=='},total:1}};
      }
      if(name==='get_packs'||name==='select_pack'||name==='import_pack')return {structuredContent:{packs:[{id:'cat'}],selected:'cat',manifest:{clips:{idle:{}}}}};
      if(name==='play_clip')return {isError:true,content:[{type:'text',text:'unknown clip'}]};
      throw Error('unexpected tool '+name);
    }
  };
  vm.runInNewContext(source,context);
  return {context,calls};
}
(async()=>{
  {
    const {context}=harness();
    const one=[],two=[];
    const first=new context.EventSource();first.onmessage=e=>one.push(JSON.parse(e.data));await drain();
    const second=new context.EventSource();second.onmessage=e=>two.push(JSON.parse(e.data));await drain();
    assert.equal(one.length,2);assert.equal(two.length,2);
    assert.equal(two[1].state,'WORKING');assert.equal(two[0].reducedMotion,true);
    first.close();second.close();
  }
  {
    const {context,calls}=harness({manifestFailures:1});
    const endpoint='/plugins/dsh-dafeiyu/manifest';
    assert.equal((await context.fetch(endpoint)).status,503);
    assert.equal((await context.fetch(endpoint)).status,200);
    assert.equal(calls.filter(c=>c.name==='get_manifest').length,2);
  }
  {
    const {context}=harness({frameFailures:1});
    assert.equal((await context.fetch('/plugins/dsh-dafeiyu/manifest')).status,200);
    const messages=[];const stream=new context.EventSource();stream.onmessage=e=>messages.push(JSON.parse(e.data));
    await drain();assert.equal(messages.filter(m=>m.kind==='state').length,0);
    context.tick();await drain();assert.equal(messages.at(-1).state,'WORKING');stream.close();
  }
  {
    const {context,calls}=harness();
    await context.fetch('/plugins/dsh-dafeiyu/manifest');
    assert.ok(context.bigfishFrames.idle);
    assert.equal((await context.fetch('/plugins/dsh-dafeiyu/packs',{method:'POST',body:JSON.stringify({action:'select',id:'cat'})})).status,200);
    assert.equal(context.bigfishFrames.idle,undefined);
    assert.equal(calls.at(-1).name,'select_pack');
    const failure=await context.fetch('/plugins/dsh-dafeiyu/play',{method:'POST',body:JSON.stringify({clip:'bad'})});
    assert.equal(failure.status,503);
    assert.equal((await failure.json()).error,'unknown clip');
  }
  {
    let release;const frameGate=new Promise(resolve=>{release=resolve;});
    const {context}=harness({frameGate});
    const old=context.fetch('/plugins/dsh-dafeiyu/manifest');await drain();
    await context.fetch('/plugins/dsh-dafeiyu/packs',{method:'POST',body:JSON.stringify({action:'select',id:'cat'})});
    release();await old;
    assert.equal(context.bigfishFrames.idle,undefined,'in-flight old-pack frames must not repopulate cache');
  }
  console.log('MCP_BRIDGE_RESULT 5 scenarios passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
