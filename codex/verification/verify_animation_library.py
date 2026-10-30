#!/usr/bin/env python3
"""Decode the complete canonical library and create a labelled contact sheet.

Maintainer check; requires Pillow (not an application runtime dependency).
No windows, screenshots, native UI controls, or user files are accessed.
"""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[2]


def verify(root, output, sources=None):
    manifest=json.loads((root/'assets/pet-manifest.json').read_text())
    inventory=json.loads((root/'assets/animation-library.json').read_text())
    names=manifest['libraryClips']
    assert len(names)==106 and len(set(names))==106
    assert set(inventory)==set(names)
    font=ImageFont.truetype('/System/Library/Fonts/PingFang.ttc',15)
    sheet=Image.new('RGB',(5*384,22*250),'#eceff3')
    draw=ImageDraw.Draw(sheet)
    total=0;blank=0;errors=[];rows={}
    for i,name in enumerate(names):
        clip=manifest['clips'][name]
        assert len(clip['frames'])==inventory[name]['frames']
        if sources:
            video=sources/clip['source']['file']
            assert hashlib.sha256(video.read_bytes()).hexdigest()==inventory[name]['sha256']
        samples={0,len(clip['frames'])//2,len(clip['frames'])-1}
        bounds=None
        for j,frame in enumerate(clip['frames']):
            path=root/'assets/pet'/frame
            assert path.resolve().is_relative_to((root/'assets/pet').resolve())
            with Image.open(path) as image:
                image.load()
                assert image.size==(640,360) and image.mode=='RGBA',(name,j,image.size,image.mode)
                alpha=image.getchannel('A');box=alpha.getbbox()
                assert alpha.getextrema()[0]==0,(name,j,'lost transparency')
                if box:
                    bounds=box if bounds is None else (min(bounds[0],box[0]),min(bounds[1],box[1]),max(bounds[2],box[2]),max(bounds[3],box[3]))
                else:blank+=1
                if j in samples:
                    slot=[0,len(clip['frames'])//2,len(clip['frames'])-1].index(j)
                    thumb=image.resize((128,72),Image.Resampling.LANCZOS)
                    x=(i%5)*384+slot*128;y=(i//5)*250+42
                    sheet.paste(thumb,(x,y),thumb)
            total+=1
        x=(i%5)*384;y=(i//5)*250
        draw.text((x+5,y+8),f'{i+1:03d} {name}',fill='#20252c',font=font)
        draw.text((x+5,y+124),f'{len(clip["frames"])} 帧 · 首 / 中 / 尾',fill='#48505c',font=font)
        rows[name]={'frames':len(clip['frames']),'alphaUnionBounds':bounds}
    output.mkdir(parents=True,exist_ok=True)
    sheet.save(output/'all-106-contact-sheet.jpg',quality=90)
    report={'clips':len(names),'framesDecoded':total,'blankFrames':blank,
            'sourceCommit':manifest['assetSource']['commit'],
            'canvas':[640,360],'lossyWebPQuality':68,'clipsDetail':rows,
            'scope':'Every canonical frame decoded and alpha inspected; source SHA verified if --sources given. Contact sheet samples first/middle/final. Does not claim lossless source-video pixel identity or OS UI acceptance.'}
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='clipsDetail'},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--out',type=Path,default=ROOT/'codex/evidence/animation-library')
    parser.add_argument('--sources',type=Path)
    args=parser.parse_args();verify(args.root,args.out,args.sources)
