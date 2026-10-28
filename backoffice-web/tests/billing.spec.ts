import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {mount,flushPromises,DOMWrapper,type VueWrapper} from '@vue/test-utils';
import Antd from 'ant-design-vue';
import http from '../src/api/http';
import BillingView from '../src/views/BillingView.vue';
import Packages from '../src/components/billing/CustomizationPackagesPanel.vue';
import Operations from '../src/components/billing/BillingOperationsPanel.vue';
import Customization from '../src/components/billing/CustomizationBillingPanel.vue';
vi.mock('../src/stores/auth',()=>({useAuthStore:()=>({hasPermission:()=>true})}));
const originalAdapter=http.defaults.adapter;
let wrappers:VueWrapper[]=[];
beforeEach(()=>localStorage.clear());
afterEach(()=>{wrappers.forEach(w=>w.unmount());wrappers=[];document.body.innerHTML='';http.defaults.adapter=originalAdapter;});
function adapter(envelope=false,initialReason:string|null='已保存的测试说明'){
 const calls:{method:string|undefined;url:string|undefined;data:any}[]=[];
 let savedDraft:any=initialReason===null?null:{expected_revision:1,access_mode:'free',diamond_price:null,currency_code:null,pro_entitlement_key:null,bundled_grants:[],terms_version:'v1',change_reason:initialReason};
 http.defaults.adapter=async config=>{
 calls.push({method:config.method,url:config.url,data:config.data?JSON.parse(config.data):undefined});
 let payload:unknown;
 const path=config.url??'';
 if(path.endsWith('/content-offers/'))payload={items:[{id:'offer-1',title:'接口解包测试贴纸',target_kind:'sticker_library',revision:1,access_mode:'free',diamond_price:null}]};
 else if(path.endsWith('/draft/')){if(config.method==='patch')savedDraft=JSON.parse(config.data);payload={draft:savedDraft};}
 else if(path.endsWith('/customization-packages/'))payload={items:[{id:'package-1',package__title:'测试排版套餐',package__code:'test',revision:1,standard_diamonds:990,pro_diamonds:890}]};
 else if(path.endsWith('/quote/'))payload={quotes:[{id:'quote-1',revision:1,standard_diamonds:990,pro_diamonds:890}],fundings:[{id:'funding-1',amount:890,status:'funded',identity__wallet_domain:'sandbox'}]};
 else if(path.endsWith('/operations/'))payload={items:[{id:'operation-1',kind:'debit',delta:-40,state:'succeeded',attempt_count:1}],cases:[{id:'case-1',kind:'测试待核查',operation_id:'operation-1'}]};
 else throw Error('Unexpected request '+path);
 return {data:envelope?{code:0,msg:'ok',data:payload}:payload,status:200,statusText:'OK',headers:{},config};
};return calls;}
function render(component:any,props?:Record<string,unknown>){const w=mount(component,{props,attachTo:document.body,global:{plugins:[Antd]}});wrappers.push(w);return w;}
describe('billing uses the shared HTTP response interceptor',()=>{
 it.each([false,true])('loads offers and saved draft when envelope=%s',async envelope=>{
  adapter(envelope);const w=render(BillingView);await flushPromises();
  expect(w.text()).toContain('接口解包测试贴纸');
  expect(w.text()).not.toContain('Cannot read properties');
  await w.findAll('button').find(b=>b.text()==='编辑策略')!.trigger('click');await flushPromises();
  expect((document.querySelector('textarea') as HTMLTextAreaElement).value).toBe('已保存的测试说明');
 });
 it('loads package, operations and commission funding from unwrapped payloads',async()=>{
  adapter();render(Packages);render(Operations);render(Customization,{requestId:'request-1',status:'submitted'});await flushPromises();
  expect(document.body.textContent).toContain('测试排版套餐');
  expect(document.body.textContent).toContain('operation-1');
  expect(document.body.textContent).toContain('测试待核查');
  expect(document.body.textContent).toContain('funding-1');
  expect(document.body.textContent).not.toContain('Cannot read properties');
 });
});


describe('billing pricing draft validation',()=>{
 it('keeps blank or whitespace reasons at the field and sends no save request',async()=>{
  const calls=adapter(false,null),w=render(BillingView);await flushPromises();
  await w.findAll('button').find(b=>b.text()==='编辑策略')!.trigger('click');await flushPromises();
  const textarea=new DOMWrapper(document.querySelector('textarea')!);
  await textarea.setValue('   ');
  const save=new DOMWrapper([...document.querySelectorAll('button')].find(b=>b.textContent?.trim()==='保存草稿')!);
  await save.trigger('click');await flushPromises();
  expect(document.body.textContent).toContain('请填写变更说明，说明本次调整的原因');
  expect(calls.filter(c=>c.method==='patch')).toHaveLength(0);
  const inspect=[...document.querySelectorAll('button')].find(b=>b.textContent?.trim()==='校验与查看影响')!;
  expect(inspect.disabled).toBe(true);
 });
 it('saves a reason and restores the saved draft without publishing',async()=>{
  const calls=adapter(false,null),w=render(BillingView);await flushPromises();
  await w.findAll('button').find(b=>b.text()==='编辑策略')!.trigger('click');await flushPromises();
  await new DOMWrapper(document.querySelector('textarea')!).setValue('  明确本次内容收费策略的用途  ');
  await new DOMWrapper([...document.querySelectorAll('button')].find(b=>b.textContent?.trim()==='保存草稿')!).trigger('click');await flushPromises();
  const patches=calls.filter(c=>c.method==='patch');
  expect(patches).toHaveLength(1);
  expect(patches[0]!.data.change_reason).toBe('明确本次内容收费策略的用途');
  expect(document.body.textContent).toContain('草稿已保存，在线策略尚未变更');
  expect(calls.some(c=>c.url?.endsWith('/publish/'))).toBe(false);
  expect([...document.querySelectorAll('button')].find(b=>b.textContent?.trim()==='校验与查看影响')!.disabled).toBe(false);
 });
});

it('loads the latest published revision instead of reusing an expired pricing draft',async()=>{
 const calls=adapter(false,null),normal=http.defaults.adapter as import('axios').AxiosAdapter;
 http.defaults.adapter=async config=>config.url?.endsWith('/draft/')&&config.method==='get'
  ? {data:{offer:{id:'offer-1',title:'接口解包测试贴纸',target_kind:'sticker_library',revision:2,access_mode:'diamond_only',diamond_price:100},draft:null,stale_draft:true},status:200,statusText:'OK',headers:{},config}
  : normal(config);
 const w=render(BillingView);await flushPromises();
 await w.findAll('button').find(b=>b.text()==='编辑策略')!.trigger('click');await flushPromises();
 expect(document.body.textContent).toContain('旧草稿已过期');
 expect((document.querySelector('#form_item_diamond_price') as HTMLInputElement).value).toBe('100');
 await new DOMWrapper(document.querySelector('textarea')!).setValue('基于第二版调整');
 await new DOMWrapper([...document.querySelectorAll('button')].find(b=>b.textContent?.trim()==='保存草稿')!).trigger('click');await flushPromises();
 expect(calls.find(c=>c.method==='patch')?.data.expected_revision).toBe(2);
});
