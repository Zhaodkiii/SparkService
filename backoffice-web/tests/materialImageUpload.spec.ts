import {afterEach,describe,it,expect,vi} from 'vitest';
import {inspectImage,prepareMaterialImage,putImageToOSS} from '../src/views/materialImageUpload';

function png(width=2,height=2,animated=false){
  const data=new Uint8Array(animated?65:45);data.set([137,80,78,71,13,10,26,10]);
  const view=new DataView(data.buffer);view.setUint32(8,13);data.set([73,72,68,82],12);view.setUint32(16,width);view.setUint32(20,height);
  let offset=33;if(animated){view.setUint32(offset,8);data.set([97,99,84,76],offset+4);offset+=20}data.set([73,69,78,68],offset+4);return data;
}
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals()});
describe('browser image preparation',()=>{
  it('uses file contents to identify PNG and rejects SVG or truncated files',()=>{
    expect(inspectImage(png(),'sticker')).toEqual({mime:'image/png',width:2,height:2});
    expect(()=>inspectImage(new TextEncoder().encode('<svg/>'),'sticker')).toThrow();
    expect(()=>inspectImage(png().slice(0,25),'sticker')).toThrow();
  });
  it('rejects animation, excessive pixels and invalid cover or preview dimensions',()=>{
    expect(()=>inspectImage(png(2,2,true),'sticker')).toThrow('动画');
    expect(()=>inspectImage(png(4096,4096),'sticker')).toThrow('总像素');
    expect(()=>inspectImage(png(512,256),'cover')).toThrow('方图');
    expect(()=>inspectImage(png(749,800),'preview')).toThrow('750');
  });
  it('rejects animated WebP before decoding',()=>{
    const data=new Uint8Array(20);data.set(new TextEncoder().encode('RIFF'));new DataView(data.buffer).setUint32(4,12,true);data.set(new TextEncoder().encode('WEBPANIM'),8);
    expect(()=>inspectImage(data,'sticker')).toThrow('动态 WebP');
  });
  function canvas(pixels:number[]){
    const close=vi.fn();vi.stubGlobal('createImageBitmap',vi.fn().mockResolvedValue({width:2,height:2,close}));
    const context={drawImage:vi.fn(),getImageData:()=>({data:new Uint8ClampedArray(pixels)})};
    vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue(context as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype,'toBlob').mockImplementation(callback=>callback(new Blob(['thumbnail'],{type:'image/png'})));
    return close;
  }
  it('generates a separate PNG thumbnail, preserves original bytes and closes decoded images',async()=>{
    const close=canvas([255,0,0,255,0,0,0,0]);const bytes=png();
    const result=await prepareMaterialImage(new File([bytes],'fake-name.jpg',{type:'image/jpeg'}),'sticker');
    expect(result.metadata.original).toMatchObject({width:2,height:2,mime:'image/png',has_transparency:true,has_visible_pixels:true});
    expect(result.metadata.thumbnail).toMatchObject({width:2,height:2,mime:'image/png'});
    expect(new Uint8Array(await result.original.arrayBuffer())).toEqual(bytes);
    expect(result.metadata.original.sha256).toHaveLength(64);expect(atob(result.metadata.original.md5)).toHaveLength(16);expect(close).toHaveBeenCalled();
  });
  it('rejects invisible or opaque stickers and always releases decoded images',async()=>{
    for(const pixels of [[0,0,0,0],[255,0,0,255]]){
      const close=canvas(pixels);await expect(prepareMaterialImage(new File([png()],'invalid.png'),'sticker')).rejects.toThrow();expect(close).toHaveBeenCalled();vi.restoreAllMocks();
    }
  });
  it('sends only signed headers and file bytes to the OSS host',async()=>{
    const sent:unknown[]=[];const headers:Record<string,string>={};
    vi.stubGlobal('XMLHttpRequest',class{
      upload={};status=200;timeout=0;onload?:()=>void;
      open(method:string,url:string){sent.push(method,url)}
      setRequestHeader(key:string,value:string){headers[key]=value}
      send(blob:Blob){sent.push(blob);this.onload?.()}
    });
    const blob=new Blob(['image']);await putImageToOSS({url:'https://test.oss-cn-beijing.aliyuncs.com/key',headers:{'Content-Type':'image/png','Content-MD5':'checksum'}},blob,()=>{});
    expect(sent).toEqual(['PUT','https://test.oss-cn-beijing.aliyuncs.com/key',blob]);expect(headers).not.toHaveProperty('Authorization');
    await expect(putImageToOSS({url:'http://localhost:2026/api/upload',headers:{}},blob,()=>{})).rejects.toThrow('OSS HTTPS');
  });
});
