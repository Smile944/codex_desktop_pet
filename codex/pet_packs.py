"""Pack-local transparent VP9 animation import; no network or executable pack code."""
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path, PurePosixPath

MAX_FILES = 400
MAX_BYTES = 512 * 1024 * 1024
MAX_OUTPUT = 1024 * 1024 * 1024
MAX_CLIPS = 160
MAX_FRAMES = 1440  # one minute at 24 fps
FPS = 24
FRAME_MS = 42


def read_jsonc(text):
    """Strip JSONC comments/trailing commas without changing string contents."""
    if len(text) > 1024 * 1024:
        raise ValueError('角色配置过大')
    output = []
    index, quoted, escaped = 0, False, False
    while index < len(text):
        c = text[index]
        if quoted:
            output.append(c)
            if escaped: escaped = False
            elif c == '\\': escaped = True
            elif c == '"': quoted = False
            index += 1
        elif c == '"':
            quoted = True;output.append(c);index += 1
        elif text[index:index+2] == '//':
            end = text.find('\n',index+2);index = len(text) if end < 0 else end
        elif text[index:index+2] == '/*':
            end = text.find('*/',index+2)
            if end < 0: raise ValueError('角色配置注释未结束')
            output.append(' ');index = end+2
        elif c == ',':
            # Remove trailing commas in a second lexical pass after comments.
            output.append(c);index += 1
        else:
            output.append(c);index += 1
    clean = ''.join(output)
    output=[];quoted=False;escaped=False
    for index,c in enumerate(clean):
        if not quoted and c == ',' and clean[index+1:].lstrip().startswith(('}',']')):
            continue
        output.append(c)
        if quoted:
            if escaped: escaped=False
            elif c == '\\':escaped=True
            elif c == '"':quoted=False
        elif c == '"':quoted=True
    try:
        return json.loads(''.join(output))
    except (ValueError, RecursionError) as exc:
        raise ValueError('角色配置不是有效 JSON/JSONC') from exc


def safe_name(value):
    if not isinstance(value,str) or not value or len(value)>120 or value in ('.','..') or any(c in value for c in '/\\\x00') or any(ord(c)<32 for c in value):
        raise ValueError('无效动画名称')
    return value


def clip_key(name):
    return hashlib.sha256(name.encode()).hexdigest()[:20]


def normalize_config(config):
    if not isinstance(config,dict) or not isinstance(config.get('animations'),dict):
        raise ValueError('缺少角色 animations 配置')
    animations=config['animations']
    names=set()
    for pool in ('idle','turn','drag','clicks'):
        values=animations.get(pool,[])
        if not isinstance(values,list) or len(values)>MAX_CLIPS:raise ValueError('无效动画池')
        names.update(safe_name(v) for v in values)
    if not animations.get('idle'):raise ValueError('至少需要一个待机动画')
    moves=animations.get('moves',{})
    if not isinstance(moves,dict) or not isinstance(moves.get('actions',[]),list):raise ValueError('无效移动动作')
    def motion_parameters(params):
        if not isinstance(params,dict):raise ValueError('无效移动参数')
        for key,value in params.items():
            if key not in ('minDist','maxDist','margin','leadSec','tailSec') or type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=10000:
                raise ValueError('无效移动参数')
    motion_parameters(moves.get('default',{}))
    for move in moves.get('actions',[]):
        if not isinstance(move,dict):raise ValueError('无效移动动作')
        names.add(safe_name(move.get('name')))
        motion_parameters(move.get('params',{}))
    categories=animations.get('categories',[])
    if not isinstance(categories,list) or len(categories)>40:raise ValueError('无效动画分类')
    for category in categories:
        if not isinstance(category,dict) or not isinstance(category.get('actions'),list):raise ValueError('无效动画分类')
        safe_name(category.get('id'))
        names.update(safe_name(v) for v in category['actions'])
        weight=category.get('weight',0)
        if type(weight) not in (int,float) or not math.isfinite(weight) or not 0<=weight<=10000:raise ValueError('无效动画权重')
    events=animations.get('events',{})
    if not isinstance(events,dict):raise ValueError('无效事件动画')
    for values in events.values():
        if not isinstance(values,list):raise ValueError('无效事件动画')
        for value in values:
            candidates=value if isinstance(value,list) else [value]
            if not candidates or len(candidates)>MAX_CLIPS:raise ValueError('无效事件动画候选')
            names.update(safe_name(v) for v in candidates)
    weights=config.get('animationWeights',{'idle':10,'turn':5,'move':5})
    if not isinstance(weights,dict):raise ValueError('无效动画权重')
    for value in weights.values():
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=10000:raise ValueError('无效动画权重')
    if not 1<=len(names)<=MAX_CLIPS:raise ValueError('动画数量超出限制')
    return animations,weights,names


def encode_video(source, target, ffmpeg):
    if ffmpeg is None:raise ValueError('未安装动画解码工具，请使用新版独立安装包')
    target.mkdir(parents=True,exist_ok=False)
    # Force the Matroska demuxer and VP9 alpha decoder; never follow a playlist URL.
    command=[str(ffmpeg),'-v','error','-nostdin','-protocol_whitelist','file,pipe',
             '-f','matroska','-c:v','libvpx-vp9','-i',str(source),'-an','-sn',
             '-vf','fps=24,scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2:color=black@0',
             '-frames:v',str(MAX_FRAMES+1),'-c:v','libwebp','-lossless','0','-q:v','68','-compression_level','4',
             str(target/'frame_%05d.webp')]
    try:
        result=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=180)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise ValueError('动画转换失败或超时') from exc
    frames=sorted(target.glob('frame_*.webp'))
    if result.returncode or not frames or len(frames)>MAX_FRAMES:
        raise ValueError('动画须为有效透明 VP9 WebM，且每段不超过 60 秒')
    if sum(p.stat().st_size for p in frames)>MAX_OUTPUT:raise ValueError('动画转换后过大')
    return frames


def create_manifest(clips, config, name, source=None):
    animations,weights,_=normalize_config(config)
    idle=animations['idle'][0]
    work=animations.get('events',{}).get('workStatus',[])
    states=('THINKING','WORKING','SUCCESS','WAITING','SUCCESS','ERROR')
    state_map={state:idle for state in ('IDLE','THINKING','WORKING','WAITING','SUCCESS','ERROR','DISCONNECTED')}
    for i,state in enumerate(states):
        if i<len(work):
            candidates=work[i] if isinstance(work[i],list) else [work[i]]
            if candidates and candidates[0] in clips:state_map[state]=candidates[0]
    for clip in clips.values():clip['loop']=False
    for clip in set(animations.get('idle',[]))|{state_map[s] for s in ('THINKING','WORKING','WAITING')}:
        clips[clip]['loop']=True
    return dict(formatVersion=1,characterId=clip_key(name),name=name,baseSize=640,
                maxFrameWidth=640,maxFrameHeight=360,contentRect=[100,0,412,344],
                clips=clips,stateMap=state_map,workingActivityMap={},idleMicroClips=[],
                idleMicroIntervalsMs={'quiet':[45000,90000],'normal':[25000,45000],'lively':[12000,22000]},
                interactionCooldownMs=1200,animations=animations,animationWeights=weights,
                clipLabels={key:key for key in clips},libraryClips=list(clips),assetSource=source or {})


def _safe_file(path, root, limit=MAX_BYTES):
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('角色包不能包含链接或外部路径')
    for parent in path.relative_to(root).parents:
        if (root/parent).is_symlink():raise ValueError('角色包不能包含链接目录')
    if path.stat().st_size>limit:raise ValueError('角色包文件过大')
    return path


def _extract_zip(source, target):
    with zipfile.ZipFile(source) as archive:
        entries=archive.infolist()
        if len(entries)>MAX_FILES or sum(i.file_size for i in entries)>MAX_BYTES:raise ValueError('角色包超过大小限制')
        for item in entries:
            path=PurePosixPath(item.filename)
            mode=item.external_attr>>16
            if path.is_absolute() or '..' in path.parts or '\\' in item.filename or '\x00' in item.filename or stat.S_ISLNK(mode):
                raise ValueError('角色包包含不安全路径')
            dest=target.joinpath(*path.parts)
            if item.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
            if dest.exists():raise ValueError('角色包含重复文件')
            dest.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(item) as inp,dest.open('wb') as out:shutil.copyfileobj(inp,out)


class PackStore:
    def __init__(self,builtin_assets,data_dir,ffmpeg=None):
        self.builtin=Path(builtin_assets).resolve()
        self.root=Path(data_dir)/'packs'
        self.ffmpeg=ffmpeg
        self.lock=threading.Lock()

    def resolve(self,identifier):
        if identifier=='builtin':return self.builtin
        if not isinstance(identifier,str) or re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',identifier) is None:
            raise ValueError('无效角色包标识')
        path=self.root/identifier
        if path.is_symlink() or not path.is_dir() or not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('角色包不存在')
        _safe_file(path/'pet-manifest.json',path,8*1024*1024)
        return path

    def _metadata(self,identifier):
        root=self.resolve(identifier)
        value=json.loads((root/'pet-manifest.json').read_text())
        return {'id':identifier,'name':str(value.get('name','原版大肥鱼' if identifier=='builtin' else identifier))[:100],
                'clipCount':len(value.get('libraryClips',value['clips']))}

    def list(self):
        result=[self._metadata('builtin')]
        if self.root.exists():
            for path in sorted(self.root.iterdir()):
                if path.name.startswith('.'):continue
                try:result.append(self._metadata(path.name))
                except (OSError,ValueError,KeyError,TypeError):continue
        return result

    def import_pack(self,path):
        if not self.lock.acquire(blocking=False):raise ValueError('已有角色包正在导入，请等待完成')
        try:
            self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
            with tempfile.TemporaryDirectory(prefix='.import-',dir=self.root) as stage:
                stage=Path(stage)
                source=Path(path).expanduser().absolute()
                if source.is_symlink():raise ValueError('请选择真实角色包文件')
                if source.suffix.lower()=='.zip' and source.is_file():
                    _safe_file(source,source.parent)
                    expanded=stage/'source';expanded.mkdir()
                    _extract_zip(source,expanded);source=expanded
                if source.is_dir():
                    configs=list(source.rglob('*-config.json'))+list(source.rglob('*-config.jsonc'))
                    configs=[p for p in configs if not p.name.startswith('.')]
                    if len(configs)!=1:raise ValueError('请选择单个角色的 <名称>-config.json 或其 ZIP')
                    source=configs[0]
                _safe_file(source,source.parent,1024*1024)
                match=re.fullmatch(r'(.+)-config\.jsonc?',source.name)
                if not match:raise ValueError('请选择 <名称>-config.json 角色配置')
                stem=safe_name(match[1])
                config=read_jsonc(source.read_text(encoding='utf-8-sig'))
                animations,_,names=normalize_config(config)
                media=source.parent/(stem+'-animation')
                if media.is_symlink():raise ValueError('角色素材目录不能是链接')
                if (media/'webm').is_dir():media=media/'webm'
                # Include all supplied VP9 clips in the manual library, not only random pools.
                videos={p.stem:p for p in media.glob('*.webm')}
                if not names.issubset(videos):raise ValueError('角色包缺少配置引用的 WebM 动画')
                if len(videos)>MAX_CLIPS:raise ValueError('角色包动画过多')
                total=0;digest=hashlib.sha256(source.read_bytes())
                for name,video in sorted(videos.items()):
                    safe_name(name);_safe_file(video,source.parent)
                    total+=video.stat().st_size
                    digest.update(name.encode());digest.update(hashlib.sha256(video.read_bytes()).digest())
                if total>MAX_BYTES:raise ValueError('角色包过大')
                identifier='pack-'+digest.hexdigest()[:24]
                if (self.root/identifier).exists():return self._metadata(identifier)
                output=stage/'converted';(output/'pet').mkdir(parents=True)
                clips={};output_size=0
                for name,video in sorted(videos.items()):
                    key=clip_key(name)
                    frames=encode_video(video,output/'pet'/key,self.ffmpeg)
                    output_size+=sum(p.stat().st_size for p in frames)
                    if output_size>MAX_OUTPUT:raise ValueError('角色包转换后过大')
                    clips[name]={'frames':[str(p.relative_to(output/'pet')) for p in frames], 'frameMs':FRAME_MS,'loop':False,
                                 'source':{'file':video.name,'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'frameCount':len(frames)}}
                pets=config.get('pets',[])
                name=pets[0].get('name',stem) if isinstance(pets,list) and pets and isinstance(pets[0],dict) else stem
                manifest=create_manifest(clips,config,str(name)[:100])
                (output/'pet-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
                # Keep pack authorship and configuration for local inspection.
                (output/'source-config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
                os.replace(output,self.root/identifier)
                return self._metadata(identifier)
        except (zipfile.BadZipFile,UnicodeError,KeyError,TypeError,RecursionError) as exc:
            raise ValueError('角色包格式无效') from exc
        finally:self.lock.release()
