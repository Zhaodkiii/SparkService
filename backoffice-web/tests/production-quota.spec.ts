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
 current_policy:{id:1,name:'开发验收策略',short_limit:3,weekly_limit:10,enabled:true},
 policies:[],tasks:[],ledger:[],account_quota:null,pagination:{total:0,page:1,page_size:25},
 service_control:{accepting:true,version:1,reason:''}}});
 wrapper=mount(View,{attachTo:document.body,global:{plugins:[Antd]}});
 await flushPromises();
 expect(wrapper.text()).toContain('开发验收策略');
 expect(wrapper.text()).toContain('按每位用户首次制作时间计算周期');
 expect(wrapper.text()).toContain('168 小时后恢复');
 expect(wrapper.text()).toContain('暂无策略');
 const button=wrapper.findAll('button').find(b=>b.text()==='新建策略');
 await button!.trigger('click');await flushPromises();
 expect(document.body.textContent).toContain('预览变更');
 expect(document.body.textContent).toContain('从每位用户首次成功开始制作计时');
});
it('shows errors with a retry entry instead of an empty success state',async()=>{
 http.defaults.adapter=async()=>{throw new Error('测试网络中断');};
 wrapper=mount(View,{global:{plugins:[Antd]}});
 await flushPromises();
 expect(wrapper.text()).toContain('测试网络中断');
 expect(wrapper.findAll('button').some(b=>b.text().replace(/\s/g,'')==='刷新')).toBe(true);
});
