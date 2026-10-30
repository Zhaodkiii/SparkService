import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {mount,flushPromises,DOMWrapper,type VueWrapper} from '@vue/test-utils';
import Antd,{Modal} from 'ant-design-vue';
import http from '../src/api/http';
import BillingView from '../src/views/BillingView.vue';
import Operations from '../src/components/billing/BillingOperationsPanel.vue';
import {policyFromOffer} from '../src/features/billing/policy';
const permissions=vi.hoisted(()=>({edit:true,publish:true}));
vi.mock('vue-router',()=>({useRoute:()=>({query:{},fullPath:'/billing'}),useRouter:()=>({push:vi.fn()}),onBeforeRouteLeave:vi.fn(),onBeforeRouteUpdate:vi.fn()}));
vi.mock('../src/stores/auth',()=>({useAuthStore:()=>({hasPermission:(p:string)=>p==='billing.change_pricing_draft'?permissions.edit:p==='billing.publish_pricing'?permissions.publish:true})}));
const originalAdapter=http.defaults.adapter;let wrappers:VueWrapper[]=[];
beforeEach(()=>{localStorage.clear();permissions.edit=true;permissions.publish=true;});
afterEach(()=>{wrappers.forEach(w=>w.unmount());wrappers=[];Modal.destroyAll();http.defaults.adapter=originalAdapter;document.body.innerHTML='';vi.restoreAllMocks();});
const offer={id:'offer-1',title:'海边旅行模板',target_kind:'template',target_id:'target-1',revision:1,access_mode:'diamond_only',diamond_price:30,currency_code:'DIAMOND',bundled_grants:[{target_kind:'sticker_library',target_id:'gift-1'}],terms_version:'original-v2',available:true};
function adapter({envelope=false,saved=false,blocked=false}:{envelope?:boolean;saved?:boolean;blocked?:boolean}={}){
 const calls:any[]=[];let body:any=saved?{...policyFromOffer(offer),change_reason:'已保存原因'}:null;
 http.defaults.adapter=async config=>{
  const data=config.data?JSON.parse(config.data):undefined;calls.push({method:config.method,url:config.url,data,params:config.params});let payload:any;
  const path=config.url??'';
  if(path.endsWith('/content-catalog/'))payload={items:[offer],total:1,page:1};
  else if(path.endsWith('/draft/')){if(config.method==='patch')body=data;payload={offer,draft:body,draft_hash:body?'hash-1':null};}
  else if(path.endsWith('/publish-preview/'))payload={draft:body,draft_hash:'hash-1',can_publish:!blocked,deliverable:true,blockers:blocked?[{code:'SALES_DISABLED',message:'钻石兑换尚未开放'}]:[],warnings:[],owned_users:1,pending_orders:0};
  else if(path.endsWith('/history/'))payload={items:[]};
  else if(path.endsWith('/content-offers/'))payload=offer;
  else throw Error('Unexpected request '+path);
  return {data:envelope?{code:0,msg:'ok',data:payload}:payload,status:200,statusText:'OK',headers:{},config};
 };return calls;
}
function render(component:any,props?:Record<string,unknown>){const w=mount(component,{props,attachTo:document.body,global:{plugins:[Antd],stubs:{RouterLink:true}}});wrappers.push(w);return w;}
async function click(label:string){const element=[...document.querySelectorAll('button')].find(b=>b.textContent?.replace(/\s/g,'')===label);expect(element,`button ${label}`).toBeTruthy();await new DOMWrapper(element!).trigger('click');await flushPromises();}
async function edit(){await click('编辑策略');}
describe('pricing operator flow',()=>{
 it.each([false,true])('loads paginated catalog with shared HTTP unwrapping (envelope=%s)',async envelope=>{const calls=adapter({envelope});const w=render(BillingView);await flushPromises();expect(w.text()).toContain('海边旅行模板');expect(calls[0].url).toContain('/content-catalog/');expect(calls[0].params.page_size).toBe(20);});
 it('searches on the server rather than filtering the current page',async()=>{const calls=adapter();const w=render(BillingView);await flushPromises();const input=w.find('input[placeholder="搜索内容名称或完整内容 ID"]');await input.setValue('九寨沟');await input.trigger('keydown',{key:'Enter',keyCode:13});await flushPromises();expect(calls.at(-1).params.q).toBe('九寨沟');expect(calls.at(-1).params.page).toBe(1);});
 it('opens a searchable picker without registering content prematurely',async()=>{const calls=adapter();render(BillingView);await flushPromises();await click('新增内容策略');expect(document.body.textContent).toContain('选择需要配置策略的内容');expect(document.querySelector('input[placeholder="内容名称 / 完整内容 ID"]')).toBeTruthy();expect(calls.some(c=>c.method==='post')).toBe(false);await click('查看现有策略');expect(calls.some(c=>c.method==='post')).toBe(false);expect(document.body.textContent).toContain('永久解锁价格');});
 it('preserves existing bundle and terms while saving a price draft',async()=>{const calls=adapter();render(BillingView);await flushPromises();await edit();await new DOMWrapper(document.querySelector('textarea')!).setValue('  调整价格  ');await click('保存草稿');const saved=calls.find(c=>c.method==='patch').data;expect(saved.bundled_grants).toEqual(offer.bundled_grants);expect(saved.terms_version).toBe('original-v2');expect(saved.change_reason).toBe('调整价格');expect(saved.expected_draft_hash).toBeNull();expect(calls.some(c=>c.url.endsWith('/publish/'))).toBe(false);});
 it('requires a reason before making any save request',async()=>{const calls=adapter();render(BillingView);await flushPromises();await edit();await new DOMWrapper(document.querySelector('textarea')!).setValue('   ');await click('保存草稿');expect(calls.some(c=>c.method==='patch')).toBe(false);expect(document.body.textContent).toContain('请填写本次变更的原因');});
 it('blocks publishing even if deliverable is true when another preflight rule fails',async()=>{adapter({saved:true,blocked:true});render(BillingView);await flushPromises();await edit();await click('校验与查看影响');expect(document.body.textContent).toContain('钻石兑换尚未开放');const publish=[...document.querySelectorAll('button')].find(b=>b.textContent?.includes('发布已校验草稿'));expect(publish?.disabled).toBe(true);});
 it('renders read-only actions without save or registration controls',async()=>{permissions.edit=false;permissions.publish=false;adapter();const w=render(BillingView);await flushPromises();expect(w.text()).not.toContain('新增内容策略');await click('查看策略');expect([...document.querySelectorAll('button')].some(b=>b.textContent==='保存草稿')).toBe(false);expect(document.body.textContent).toContain('当前为只读模式');});
 it('asks before closing a dirty draft',async()=>{adapter();render(BillingView);await flushPromises();await edit();const confirm=vi.spyOn(Modal,'confirm');await new DOMWrapper(document.querySelector('textarea')!).setValue('未保存说明');await new DOMWrapper(document.querySelector('.ant-drawer-close')!).trigger('click');expect(confirm).toHaveBeenCalled();});
});
describe('wallet investigation',()=>{
 it('shows a pending compensation distinctly from confirmed return',async()=>{http.defaults.adapter=async config=>({config,status:200,statusText:'OK',headers:{},data:config.url?.endsWith('/operations/')?{items:[{id:'op-1',name:'用户甲',account_id:1,title:'海边旅行',delta:-30,kind:'debit',state:'succeeded',environment:'sandbox',compensation:{id:'refund-1',state:'prepared',amount:30}}],total:1}:{id:'op-1',name:'用户甲',title:'海边旅行',delta:-30,kind:'debit',state:'succeeded',environment:'sandbox',compensation:{id:'refund-1',state:'prepared',amount:30},can_compensate:false,compensation_reason:'此笔扣钻已提交补偿',revoked_grants:[],cases:[]}});render(Operations,{environment:'sandbox'});await flushPromises();await click('核查详情');expect(document.body.textContent).toContain('补偿单 refund-1');expect(document.body.textContent).toContain('待处理');expect(document.body.textContent).not.toContain('补偿已确认完成');expect([...document.querySelectorAll('button')].some(b=>b.textContent==='申请钻石补偿')).toBe(false);});
});
