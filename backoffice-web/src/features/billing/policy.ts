export const kinds = [{value:'template',label:'手帐模板'},{value:'sticker_library',label:'贴纸 / 背景包'},{value:'font',label:'字体'}];
export const modes = [{value:'free',label:'免费使用'},{value:'pro_only',label:'Pro 专享'},{value:'diamond_only',label:'钻石永久解锁'},{value:'pro_or_diamond',label:'Pro 或钻石永久解锁'}];
export const kindLabel=(v:string)=>kinds.find(x=>x.value===v)?.label||v;
export const modeLabel=(v:string|null)=>modes.find(x=>x.value===v)?.label||'待配置';
export const priceLabel=(p:any)=>!p?.access_mode?'待配置':['diamond_only','pro_or_diamond'].includes(p.access_mode)?`${p.diamond_price ?? '未填写'} 钻石`:'无需钻石';
export const policyLabel=(p:any)=>`${modeLabel(p?.access_mode)}${['diamond_only','pro_or_diamond'].includes(p?.access_mode)?' · '+priceLabel(p):''}`;
export const formatDate=(v:string)=>v?new Date(v).toLocaleString('zh-CN',{hour12:false}):'—';
export function policyFromOffer(offer:any){return {expected_revision:offer.revision,access_mode:offer.access_mode||'free',diamond_price:offer.diamond_price??null,currency_code:offer.currency_code??null,pro_entitlement_key:offer.pro_entitlement_key??null,bundled_grants:JSON.parse(JSON.stringify(offer.bundled_grants||[])),terms_version:offer.terms_version||'content-personal-v1',change_reason:''};}
export function normalizePolicy(value:any){const diamond=['diamond_only','pro_or_diamond'].includes(value.access_mode);return {...value,change_reason:(value.change_reason||'').trim(),diamond_price:diamond?value.diamond_price:null,currency_code:diamond?'DIAMOND':null,pro_entitlement_key:['pro_only','pro_or_diamond'].includes(value.access_mode)?'member':null};}
export function rights(mode:string){return [
 {user:'普通用户，未永久解锁',result:mode==='free'?'免费使用':mode==='pro_only'?'需开通 Pro':'支付钻石后永久解锁'},
 {user:'Pro 有效期内',result:mode==='diamond_only'?'仍需支付钻石永久解锁':'可使用，无需另付钻石'},
 {user:'Pro 到期，未永久解锁',result:mode==='free'?'仍可免费使用':mode==='pro_only'?'需恢复 Pro 权益':'需支付钻石永久解锁'},
 {user:'已永久解锁',result:'保留原许可，不重复收费'},
];}
