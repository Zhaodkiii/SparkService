import {afterEach,describe,expect,it,vi} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import Antd from 'ant-design-vue';
import http from '../src/api/http';
import View from '../src/views/BillingTransactionsView.vue';
vi.mock('vue-router',()=>({useRoute:()=>({query:{}})}));
vi.mock('../src/stores/auth',()=>({useAuthStore:()=>({hasPermission:()=>true})}));
const original=http.defaults.adapter;let wrapper:any;
afterEach(()=>{wrapper?.unmount();http.defaults.adapter=original;document.body.innerHTML='';});
describe('transaction center',()=>{
 it('uses real response unwrapping, production default and unknown amount',async()=>{
  let requested:any;
  http.defaults.adapter=async config=>{requested=config;return {config,status:200,statusText:'OK',headers:{},data:{code:0,msg:'ok',data:{items:[{id:'one',name:'测试用户',account_id:1,environment:'production',product:'60 钻',amount:null,payment_state:'confirmed',delivery_state:'grant_pending',expected_units:60,verified_units:null}],total:1,summary:{amounts:[],unknown_amounts:1},unlinked_events:0,pending_topups:1}}};};
  wrapper=mount(View,{global:{plugins:[Antd],stubs:{RouterLink:true}}});await flushPromises();
  expect(requested.url).toBe('/api/v1/billing/manage/transactions/');expect(requested.params.environment).toBe('production');
  expect(wrapper.text()).toContain('测试用户');expect(wrapper.text()).toContain('金额待确认');expect(wrapper.text()).toContain('到账待确认');expect(wrapper.text()).toContain('超过 5 分钟');
 });
});
