#!/usr/bin/env python3
"""Run on an operator workstation, NEVER on the bandwidth-limited API host.
Requires requests, fonttools, Pillow. Tokens are read only from environment.
"""
import argparse
import hashlib
import io
import os
import time
import tempfile
from pathlib import Path


def inspect_file(path, kind):
    if kind == 'font':
        from fontTools.ttLib import TTFont
        with TTFont(path, lazy=False) as font:
            if 'fvar' in font: raise ValueError('可变字体尚未开放，请选择静态 TTF/OTF')
            name=font['name'].getDebugName(6)
            if not name:raise ValueError('字体缺少 PostScript 名称')
            return {'faces':[{'postscript_name':name,'family':font['name'].getDebugName(1),'label':font['name'].getDebugName(2) or 'Regular'}],
                    'variable':False,'glyph_count':len(font.getBestCmap() or {}),'parser':'fonttools-static-v1'}
    if kind in ('cover','preview'):
        from PIL import Image
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            return {'width':img.width,'height':img.height,'format':img.format,'parser':'pillow-v1'}
    if path.stat().st_size == 0:raise ValueError('空授权文件')
    return {'parser':'license-file-v1'}


def specimen(font_path, output, text, background='#FFF6EB', color='#54483E'):
    """Real glyph rendering; fail on missing glyphs, never substitute another font."""
    from fontTools.ttLib import TTFont
    from PIL import Image, ImageDraw, ImageFont
    with TTFont(font_path) as font:
        cmap=font.getBestCmap() or {}
        missing=[c for c in text if not c.isspace() and ord(c) not in cmap]
        if missing:raise ValueError('小样缺字：'+''.join(dict.fromkeys(missing)))
    img=Image.new('RGB',(1024,1024),background);d=ImageDraw.Draw(img)
    for x,y in [(150,180),(850,780),(180,850)]:
        for dx,dy in [(0,-26),(26,0),(0,26),(-26,0)]:d.ellipse((x+dx-20,y+dy-20,x+dx+20,y+dy+20),fill='#F8C9D9')
        d.ellipse((x-12,y-12,x+12,y+12),fill='#EFC775')
    lines=text.split('\n')
    if len(lines)==1 and len(text)>5:lines=[text[:len(text)//2],text[len(text)//2:]]
    size=130
    while size>30:
        f=ImageFont.truetype(str(font_path),size)
        if max(d.textbbox((0,0),line,font=f)[2] for line in lines)<800:break
        size-=4
    line_height=size*1.6;y=(1024-len(lines)*line_height)/2
    for line in lines:
        box=d.textbbox((0,0),line,font=f);x=(1024-(box[2]-box[0]))/2-box[0]
        d.text((x,y-box[1]),line,font=f,fill=color);y+=line_height
    img.save(output)


def run_once(base, token):
    import requests
    session=requests.Session();session.headers['Authorization']='Bearer '+token
    endpoint=base.rstrip('/')+'/api/v1/fonts/processor/'
    def call(body):
        r=session.post(endpoint,json=body,timeout=30);r.raise_for_status();return r.json()
    job=call({'action':'claim'})['job']
    if not job:return False
    identity={'id':job['id'],'token':job['token']}
    try:
        with tempfile.TemporaryDirectory(prefix='font-worker-') as tmp:
            path=Path(tmp)/'resource';sha=hashlib.sha256();total=0;heartbeat=time.monotonic()
            # No service authorization header is sent to OSS.
            with requests.get(job['url'],stream=True,timeout=(15,60)) as response:
                response.raise_for_status()
                with path.open('wb') as out:
                    for chunk in response.iter_content(1024*1024):
                        total+=len(chunk)
                        if total>job['byte_size']:raise ValueError('文件超过声明大小')
                        sha.update(chunk);out.write(chunk)
                        if time.monotonic()-heartbeat>45:call({'action':'heartbeat',**identity});heartbeat=time.monotonic()
            if total!=job['byte_size'] or sha.hexdigest()!=job['sha256']:raise ValueError('文件长度或 SHA256 不一致')
            metadata=inspect_file(path,job['kind'])
            call({'action':'complete',**identity,'sha256':sha.hexdigest(),'metadata':metadata})
    except Exception as exc:
        # Avoid leaking signed URLs or transport headers in task errors.
        call({'action':'fail',**identity,'error':'字体验证失败：'+(str(exc)[:200] if isinstance(exc,ValueError) else type(exc).__name__)})
    return True

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');parser.add_argument('--specimen');parser.add_argument('--output');parser.add_argument('--text',default='把日子写成诗')
    args=parser.parse_args()
    if args.specimen:specimen(Path(args.specimen),args.output,args.text)
    else:
        base=os.environ['FONT_API_BASE'];token=os.environ['FONT_PROCESSOR_TOKEN']
        while True:
            worked=run_once(base,token)
            if args.once:break
            if not worked:time.sleep(10)
