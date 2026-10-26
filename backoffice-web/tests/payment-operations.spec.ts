import {describe,it,expect,vi,beforeEach,afterEach} from 'vitest';
import {mount,flushPromises,type VueWrapper} from '@vue/test-utils';
import {createRouter,createMemoryHistory} from 'vue-router';
import Antd from 'ant-design-vue';
import Operations from '../src/components/print/PaymentOperations.vue';
const api=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}));
vi.mock('../src/api/http',()=>({default:api}));
const refund={id:'cb45d950-b293-49de-b333-937f991f42ab',order_id:'3a53b52e-0721-46c5-81a0-1c3b79c37629',attempt_id:'payment',title:'苏州慢慢走',channel:'alipay',amount:100,state:'blocked',order_state:'cancelled',payment_state:'succeeded',error_category:'balance',error_code:'ACQ.SELLER_BALANCE_NOT_ENOUGH',last_error:'商家可用余额不足，退款受阻',recovery_action:'请补足余额后重试',retry_mode:'auto',failure_count:7,created_at:'2026-10-24T09:00:00Z',checked_at:'2026-10-24T09:12:00Z',next_check_at:'2026-10-25T00:00:00Z'};
let w:VueWrapper|undefined;
beforeEach(()=>{api.get.mockReset();api.post.mockReset();api.get.mockImplementation((url:string)=>Promise.resolve(url.endsWith('overview/')?{blocked:1,outstanding_refund_fen:100}:url.endsWith('audit/')?{count:0,results:[]}:{count:1,results:[refund]}));api.post.mockResolvedValue(refund)});
afterEach(()=>{w?.unmount();document.body.innerHTML=''});
async function page(access={view:true,query:true,refund:true,orders:true}){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<div/>'}}]});await router.push('/');await router.isReady();w=mount(Operations,{props:{kind:'refunds',access,refreshKey:0},attachTo:document.body,global:{plugins:[Antd,router]}});await flushPromises();return w}
const find=(text:string)=>Array.from(document.querySelectorAll('button')).find(b=>b.textContent?.replace(/\s/g,'')===text)!;
async function click(text:string){expect(find(text)).toBeTruthy();find(text).click();await flushPromises()}
describe('payment operations',()=>{
 it('shows actionable balance failures, Beijing time and linked states without raw timestamps',async()=>{await page();const text=w!.text();expect(text).toContain('余额不足');expect(text).toContain('补足余额');expect(text).toContain('失败 7 次');expect(text).toContain('17:00:00');expect(text).not.toContain('T09:00:00Z');expect(text).toContain('订单已取消');expect(text).toContain('原支付：支付成功');expect(text).toContain('不代表可用余额')});
 it('queries without submitting a retry or requiring a money-action confirmation',async()=>{await page();await click('查询渠道结果');expect(api.post).toHaveBeenCalledWith('/api/admin/v1/print/payments/refunds/',{id:refund.id,action:'query',confirmed:false});expect(document.body.textContent).not.toContain('核对退款操作')});
 it('requires an explicit confirmation before retry and carries the original refund id',async()=>{await page();await click('重试退款');expect(api.post).not.toHaveBeenCalled();expect(document.body.textContent).toContain('核对退款操作');expect(document.body.textContent).toContain(refund.order_id);const ok=document.querySelector('.ant-modal-footer .ant-btn-primary') as HTMLButtonElement;expect(ok).toBeTruthy();ok.click();await flushPromises();expect(api.post).toHaveBeenCalledWith('/api/admin/v1/print/payments/refunds/',{id:refund.id,action:'retry',confirmed:true})});
 it('refreshes the latest record after an operation failure without hiding the reason',async()=>{await page();api.post.mockRejectedValueOnce(new Error('商家可用余额不足'));await click('查询渠道结果');expect(w!.text()).toContain('商家可用余额不足');expect(api.get.mock.calls.filter(c=>c[0].endsWith('refunds/')).length).toBeGreaterThan(1)});
 it('labels aggregate queue filters in Chinese rather than exposing internal codes',async()=>{await page();const queue=Array.from(document.querySelectorAll('.queues button')).find(b=>b.textContent?.includes('退款受阻')) as HTMLButtonElement;queue.click();await flushPromises();expect(w!.text()).toContain('全部受阻退款');expect(w!.text()).not.toContain('blocked_all');expect(api.get).toHaveBeenCalledWith('/api/admin/v1/print/payments/refunds/',expect.objectContaining({params:expect.objectContaining({queue:'blocked',state:'blocked_all'})}))});
 it('hides all query and retry controls for read-only finance users',async()=>{await page({view:true,query:false,refund:false,orders:false});expect(find('查询渠道结果')).toBeUndefined();expect(find('重试退款')).toBeUndefined();expect(find('详情')).toBeTruthy()});
});
