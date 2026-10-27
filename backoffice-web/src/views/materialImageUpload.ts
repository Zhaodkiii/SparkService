import {md5,sha256} from 'hash-wasm';

export interface ImageMetadata {
  byte_size:number; width:number; height:number; mime:string; sha256:string; md5:string;
  has_visible_pixels?:boolean; has_transparency?:boolean;
}
export interface UploadTarget {url:string; headers:Record<string,string>}
const invalid=()=>new Error('图片格式损坏或不支持，请选择静态 PNG、WebP 或 JPEG');
const ascii=(data:Uint8Array,start:number,length:number)=>String.fromCharCode(...data.subarray(start,start+length));

// Inspect the container before decoding, including animated PNG/WebP and pixel limits.
export function inspectImage(data:Uint8Array,purpose:string) {
  const view=new DataView(data.buffer,data.byteOffset,data.byteLength);
  let mime='',width=0,height=0;
  if(data.length>=24 && data[0]===137 && ascii(data,1,7)==='PNG\r\n\x1a\n') {
    mime='image/png';let ended=false;
    for(let offset=8;offset+12<=data.length;) {
      const length=view.getUint32(offset),type=ascii(data,offset+4,4);
      if(offset+12+length>data.length)throw invalid();
      if(type==='acTL')throw new Error('不支持动画 PNG，请选择静态图片');
      if(type==='IHDR'){if(offset!==8||length!==13)throw invalid();width=view.getUint32(offset+8);height=view.getUint32(offset+12)}
      offset+=12+length;
      if(type==='IEND'){ended=true;break}
    }
    if(!ended)throw invalid();
  } else if(data.length>=20 && ascii(data,0,4)==='RIFF' && ascii(data,8,4)==='WEBP') {
    mime='image/webp';if(view.getUint32(4,true)+8!==data.length)throw invalid();
    for(let offset=12;offset+8<=data.length;) {
      const type=ascii(data,offset,4),length=view.getUint32(offset+4,true),start=offset+8;
      if(start+length>data.length)throw invalid();
      if(type==='ANIM'||type==='ANMF'||(type==='VP8X'&&(data[start]!&2)))throw new Error('不支持动态 WebP，请选择静态图片');
      if(type==='VP8X'&&length>=10){width=1+data[start+4]!+(data[start+5]!<<8)+(data[start+6]!<<16);height=1+data[start+7]!+(data[start+8]!<<8)+(data[start+9]!<<16)}
      if(!width&&type==='VP8 '&&length>=10&&ascii(data,start+3,3)==='\x9d\x01\x2a'){width=view.getUint16(start+6,true)&0x3fff;height=view.getUint16(start+8,true)&0x3fff}
      if(!width&&type==='VP8L'&&length>=5&&data[start]===0x2f){const bits=view.getUint32(start+1,true);width=1+(bits&0x3fff);height=1+((bits>>>14)&0x3fff)}
      offset=start+length+(length%2);
    }
  } else if(data.length>=4 && data[0]===255 && data[1]===216) {
    mime='image/jpeg';
    for(let offset=2;offset+4<=data.length;) {
      if(data[offset++]!==255)throw invalid();
      while(data[offset]===255)offset++;
      const marker=data[offset++]!;
      if(marker===0xda||marker===0xd9)break;
      if(marker===1||(marker>=0xd0&&marker<=0xd7))continue;
      if(offset+2>data.length)throw invalid();
      const length=view.getUint16(offset);
      if(length<2||offset+length>data.length)throw invalid();
      if(marker>=0xc0&&marker<=0xcf&&![0xc4,0xc8,0xcc].includes(marker)){
        if(length<8)throw invalid();height=view.getUint16(offset+3);width=view.getUint16(offset+5);
      }
      offset+=length;
    }
  } else throw invalid();
  validateDimensions(width,height,purpose);
  if(purpose==='sticker'&&mime==='image/jpeg')throw new Error('贴纸请选择含透明区域的 PNG 或 WebP');
  return {mime,width,height};
}

function validateDimensions(width:number,height:number,purpose:string) {
  if(!width||!height)throw invalid();
  if(Math.max(width,height)>(purpose==='sticker'?4096:8192)||width*height>(purpose==='sticker'?16_000_000:24_000_000))throw new Error('图片尺寸或总像素超过限制');
  if(purpose==='cover'&&(width!==height||width<512))throw new Error('封面须为至少 512×512 的方图');
  if(purpose==='preview'&&width<750)throw new Error('展示图宽度至少 750 像素');
}

async function describe(blob:Blob,width:number,height:number,mime:string):Promise<ImageMetadata> {
  const bytes=new Uint8Array(await blob.arrayBuffer());
  const [digest,checksum]=await Promise.all([sha256(bytes),md5(bytes)]);
  const encoded=btoa(String.fromCharCode(...checksum.match(/../g)!.map(pair=>parseInt(pair,16))));
  return {byte_size:blob.size,width,height,mime,sha256:digest,md5:encoded};
}

export async function prepareMaterialImage(file:File,purpose:string) {
  if(!file.size||file.size>(purpose==='sticker'?10:15)*1024*1024)throw new Error('文件为空或超过大小限制');
  const bytes=new Uint8Array(await file.arrayBuffer());
  const {mime}=inspectImage(bytes,purpose);
  const original=new Blob([bytes],{type:mime});
  let bitmap:ImageBitmap;
  try {bitmap=await createImageBitmap(original)} catch {throw new Error('图片无法解码，请重新导出后上传')}
  const canvas=document.createElement('canvas');
  try {
    const {width,height}=bitmap;validateDimensions(width,height,purpose);
    canvas.width=width;canvas.height=height;
    const context=canvas.getContext('2d',{willReadFrequently:true});
    if(!context)throw new Error('浏览器不支持图片处理，请更换浏览器');
    context.drawImage(bitmap,0,0);
    const pixels=context.getImageData(0,0,width,height).data;
    let visible=false,transparent=false;
    for(let index=3;index<pixels.length;index+=4){visible ||= pixels[index]!>0;transparent ||= pixels[index]!<255;if(visible&&transparent)break}
    if(!visible)throw new Error('图片没有可见内容');
    if(purpose==='sticker'&&!transparent)throw new Error('贴纸必须包含实际透明像素');
    const ratio=Math.min(1,256/Math.max(width,height));
    canvas.width=Math.max(1,Math.round(width*ratio));canvas.height=Math.max(1,Math.round(height*ratio));
    context.drawImage(bitmap,0,0,canvas.width,canvas.height);
    const thumbnail=await new Promise<Blob>((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('缩略图生成失败')),'image/png'));
    const [originalInfo,thumbnailInfo]=await Promise.all([describe(original,width,height,mime),describe(thumbnail,canvas.width,canvas.height,'image/png')]);
    return {original,thumbnail,metadata:{original:{...originalInfo,has_visible_pixels:visible,has_transparency:transparent},thumbnail:thumbnailInfo}};
  } finally {bitmap.close();canvas.width=1;canvas.height=1}
}

export function putImageToOSS(target:UploadTarget,blob:Blob,onProgress:(value:number)=>void):Promise<void> {
  const url=new URL(target.url);
  if(url.protocol!=='https:'||!url.hostname.endsWith('.aliyuncs.com'))return Promise.reject(new Error('上传地址必须为 OSS HTTPS 地址'));
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();xhr.open('PUT',target.url);xhr.timeout=120000;
    for(const [key,value] of Object.entries(target.headers))xhr.setRequestHeader(key,value);
    xhr.upload.onprogress=event=>{if(event.lengthComputable)onProgress(event.loaded/event.total)};
    xhr.onload=()=>{if(xhr.status>=200&&xhr.status<300){onProgress(1);resolve()}else reject(new Error(xhr.status===403?'OSS 上传授权失效或权限不足，请重试':'OSS 上传失败，请重试'))};
    xhr.onerror=()=>reject(new Error('无法连接 OSS，请检查网络和 OSS 跨域配置'));
    xhr.ontimeout=()=>reject(new Error('OSS 上传超时，请重试'));
    xhr.onabort=()=>reject(new Error('上传已取消'));
    xhr.send(blob);
  });
}
