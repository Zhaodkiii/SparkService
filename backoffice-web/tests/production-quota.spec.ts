import {afterEach,expect,it,vi} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import Antd from 'ant-design-vue';
import View from '../src/views/AIProductionView.vue';
import http from '../src/api/http';
vi.mock('../src/stores/auth',()=>({useAuthStore:()=>({hasPermission:()=>true})}));
vi.mock('vue-router',()=>({useRoute:()=>({query:{tab:'policies'}}),useRouter:()=>({replace:vi.fn()})}));
let wrapper:ReturnType<typeof mount>|undefined;
const original=http.defaults.adapter;
afterEach(()=>{wrapper?.unmount();http.defaults.adapter=original;document.body.innerHTML='';});
it('shows the published quota and separates per-user reset from policy time',async()=>{
 http.defaults.adapter=async config=>({config,status:200,statusText:'OK',headers:{},data:{
 current_policy:{id:1,name:'开发验收策略',free_weekly_limit_points:'10',short_limit_points:'25',weekly_limit_points:'100',rates:{},enabled:true},
 policies:[],tasks:[],ledger:[],account_quota:null,pagination:{total:0,page:1,page_size:25},
 service_control:{accepting:true,version:1,reason:''}}});
 wrapper=mount(View,{attachTo:document.body,global:{plugins:[Antd]}});
 await flushPromises();
 expect(wrapper.text()).toContain('开发验收策略');
 expect(wrapper.text()).toContain('AI 制作用量');
 expect(wrapper.text()).toContain('Pro · 5 小时');
 const button=wrapper.findAll('button').find(b=>b.text()==='新建策略');
 await button!.trigger('click');await flushPromises();
 expect(document.body.textContent).toContain('预览发布');
 expect(document.body.textContent).toContain('每千输出 token');
});
it('shows errors with a retry entry instead of an empty success state',async()=>{
 http.defaults.adapter=async()=>{throw new Error('测试网络中断');};
 wrapper=mount(View,{global:{plugins:[Antd]}});
 await flushPromises();
 expect(wrapper.text()).toContain('测试网络中断');
 expect(wrapper.findAll('button').some(b=>b.text().replace(/\s/g,'')==='刷新')).toBe(true);
});
