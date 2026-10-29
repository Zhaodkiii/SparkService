// Validate actual cmap coverage before browser rendering; FontFace alone can silently fall back.
export function missingFontCharacters(buffer:ArrayBuffer,text:string):string[]{
 const v=new DataView(buffer);const check=(o:number,n:number)=>{if(o<0||o+n>v.byteLength)throw new Error('字体表损坏')};
 const u16=(o:number)=>{check(o,2);return v.getUint16(o)};const u32=(o:number)=>{check(o,4);return v.getUint32(o)};
 check(0,12);let cmap=-1;const count=u16(4);if(count>200)throw new Error('字体表数量无效');
 for(let i=0;i<count;i++){const p=12+i*16;check(p,16);if(u32(p)===0x636d6170){cmap=u32(p+8);check(cmap,u32(p+12));break}}
 if(cmap<0)throw new Error('字体没有字符映射');const maps:number[]=[];
 for(let i=0;i<u16(cmap+2);i++){const r=cmap+4+i*8,platform=u16(r),encoding=u16(r+2),p=cmap+u32(r+4);if(platform===0||(platform===3&&[1,10].includes(encoding))){if([4,12].includes(u16(p)))maps.push(p)}}
 if(!maps.length)throw new Error('暂不支持此字体字符映射');
 const has=(code:number)=>maps.some(p=>{if(u16(p)===12){const n=u32(p+12);if(n>100000)throw new Error('字符映射超限');for(let i=0;i<n;i++){const a=p+16+i*12,start=u32(a),end=u32(a+4);if(code>=start&&code<=end)return u32(a+8)+code-start!==0}return false}
 if(code>65535)return false;const n=u16(p+6)/2;if(n>32768)throw new Error('字符映射超限');const ends=p+14,starts=ends+n*2+2,deltas=starts+n*2,ranges=deltas+n*2;
 for(let i=0;i<n;i++){if(code<u16(starts+i*2)||code>u16(ends+i*2))continue;const delta=u16(deltas+i*2),range=u16(ranges+i*2);if(!range)return ((code+delta)&65535)!==0;const glyph=u16(ranges+i*2+range+(code-u16(starts+i*2))*2);return glyph!==0&&((glyph+delta)&65535)!==0}return false});
 return [...new Set(Array.from(text).filter(c=>!c.trim()?false:!has(c.codePointAt(0)!)))];
}
