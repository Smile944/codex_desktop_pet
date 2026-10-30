#!/usr/bin/env python3
"""Rebuild the pinned 106-clip library from upstream VP9-alpha WebM sources.

Example: python3 scripts/import_full_library.py --source /path/dsh-pet --ffmpeg /path/ffmpeg
The source tree must contain assets/webm and config.jsonc. Keeps all 640x360 pixels.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'codex'))
from pet_packs import read_jsonc, normalize_config, encode_video, create_manifest, clip_key

COMMIT='34cf7ec4dd1ca99a9a9ac5bcb4571d887862e226'
REPOSITORY='https://github.com/PC2005-cloud/dsh-pet'


def rebuild(source,ffmpeg,output=ROOT):
    source,output=Path(source),Path(output)
    config_path=source/'assets/config.jsonc'
    if not config_path.exists():config_path=source/'config.jsonc'
    config=read_jsonc(config_path.read_text())
    normalize_config(config)
    videos=sorted((source/'assets/webm').glob('*.webm'))
    if len(videos)!=106:raise ValueError('Expected exactly 106 source WebM clips')
    previous=json.loads((output/'assets/pet-manifest.json').read_text())
    output_root=output/'assets'
    with tempfile.TemporaryDirectory(prefix='library-',dir=output/'codex/dist') as stage:
        stage=Path(stage);pet=stage/'pet';pet.mkdir()
        def convert(video):
            name=video.stem;key=clip_key(name)
            frames=encode_video(video,pet/key,ffmpeg)
            clip={'frames':[str(p.relative_to(pet)) for p in frames],'frameMs':42,'loop':False,
                  'source':{'file':video.name,'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),
                            'startFrame':0,'endFrame':len(frames),'frameCount':len(frames)}}
            return name,clip
        clips={}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for name,clip in pool.map(convert,videos):
                clips[name]=clip
                print(name,len(clip['frames']),flush=True)
        manifest=create_manifest(clips,config,'原版大肥鱼 · 完整动画库',source={
            'repository':REPOSITORY,'commit':COMMIT,'directory':'dsh-pet/assets/webm',
            'fps':24,'crop':[0,0,640,360],'webpQuality':68,
            'decoder':'libvpx-vp9 (WebM alpha BlockAdditions)',
            'sourceCount':106,'converterSha256':hashlib.sha256(Path(ffmpeg).read_bytes()).hexdigest()})
        # Keep the existing semantic names as references to canonical frames (no duplication).
        for name,old in previous['clips'].items():
            if name in clips:continue
            canonical=Path(old['source']['file']).stem
            full=clips[canonical]
            start=old['source'].get('startFrame',0);end=old['source'].get('endFrame',len(full['frames']))
            # An existing full clip should use the current full source, sliced drag stays sliced.
            if start==0 and end==old['source'].get('frameCount'):end=len(full['frames'])
            manifest['clips'][name]={**full,'frames':full['frames'][start:end],'loop':old['loop'],
                                     'source':{**full['source'],'startFrame':start,'endFrame':end}}
            manifest['clipLabels'][name]=canonical
        for key in ('stateMap','workingActivityMap','idleMicroClips','idleMicroIntervalsMs','interactionCooldownMs'):
            manifest[key]=previous[key]
        library={name:{'sha256':clip['source']['sha256'],'frames':len(clip['frames'])} for name,clip in clips.items() if name in manifest['libraryClips']}
        # The old corpus remains intact until every clip has successfully converted.
        backup=output_root/'pet.previous'
        if backup.exists():raise ValueError('Remove/recover previous asset backup before rebuilding')
        os.replace(output_root/'pet',backup)
        try:
            os.replace(pet,output_root/'pet')
            (stage/'pet-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
            os.replace(stage/'pet-manifest.json',output_root/'pet-manifest.json')
        except BaseException:
            if (output_root/'pet').exists():shutil.rmtree(output_root/'pet')
            os.replace(backup,output_root/'pet');raise
        shutil.rmtree(backup)
        (output_root/'animation-library.json').write_text(json.dumps(library,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'sourceCount':len(videos),'canonicalFrames':sum(v['frames'] for v in library.values()),
                          'bytes':sum(p.stat().st_size for p in (output_root/'pet').rglob('*.webp'))}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--ffmpeg',type=Path,required=True)
    args=parser.parse_args();rebuild(args.source,args.ffmpeg)
