import {createImagePool} from './asset-cache'
export async function api(path:string){const r=await fetch('/api/public/v1/'+path);if(!r.ok)throw Error(`服务请求失败（${r.status}），请重试`);const d=await r.json();return d.data??d}
export function base(b:any){return `books/${b.sourceId||b.id}/${b.version}/`}
function decodeImage(src:string):Promise<HTMLImageElement>{return new Promise((resolve,reject)=>{const i=new Image();i.crossOrigin='anonymous';const timer=setTimeout(()=>{i.onload=i.onerror=null;i.src='';reject(Error('素材加载超时，请重试'))},25000);i.onload=()=>{clearTimeout(timer);resolve(i)};i.onerror=()=>{clearTimeout(timer);reject(Error('图片加载失败，请重试'))};i.src=localAsset(src)})}
const pool=createImagePool(decodeImage,i=>i.naturalWidth*i.naturalHeight*4)
export function image(src:string):Promise<HTMLImageElement>{return src.startsWith('data:')||src.startsWith('blob:')?decodeImage(src):pool.get(src)}

// Development-only same-origin bridge to the fixed OSS bucket. Production requires OSS CORS.
function localAsset(src:string){if(import.meta.env.DEV&&src.startsWith('https://zhaodkdream.oss-cn-beijing.aliyuncs.com/traveldiary/presets/blobs/')){const u=new URL(src);return '/__oss'+u.pathname+u.search}return src}
