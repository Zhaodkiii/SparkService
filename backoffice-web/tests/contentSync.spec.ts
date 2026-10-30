import {describe,it,expect,vi,afterEach} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import Antd,{Select} from 'ant-design-vue';
import View from '../src/views/ContentSyncView.vue';
const mocks=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}));
vi.mock('../src/api/http',()=>({default:mocks}));
afterEach(()=>{vi.clearAllMocks();document.body.innerHTML='';});
describe('content sync batch',()=>{
 it('only previews before explicit confirmation and includes dependency rows',async()=>{
 const row={key:'template:t',kind:'template',type:'template',id:'t',title:'旅行',version:2,selectable:true};
 mocks.get.mockImplementation((p:string)=>Promise.resolve(p.endsWith('catalog/')?{enabled:true,items:[row]}:[]));
 mocks.post.mockResolvedValue({id:'b',state:'preview',plan_hash:'hash',entries:[{...row,state:'pending',reason:'手动选择'}]});
 const w=mount(View,{attachTo:document.body,global:{plugins:[Antd]}});await flushPromises();
 const button=(s:string)=>Array.from(document.querySelectorAll('button')).find(b=>b.textContent?.replace(/\s/g,'').startsWith(s))!;
 button('选择所有可同步资源').click();await flushPromises();button('预览同步清单').click();await flushPromises();
 expect(mocks.post).toHaveBeenCalledTimes(1);expect(mocks.post).toHaveBeenCalledWith('/api/admin/v1/content-sync/batches/',{selection:[{kind:'template',id:'t'}]});
 expect(document.body.textContent).toContain('确认以上版本并同步到生产');w.unmount();
 });
 it('hides completed resources by default and disables them in completed view',async()=>{
 const complete={key:'template:done',kind:'template',type:'template',id:'done',title:'已经同步的九寨沟',version:2,selectable:false,sync_state:'succeeded',sync_label:'已同步当前版本'};
 const pending={...complete,key:'template:todo',id:'todo',title:'等待同步的雨崩',selectable:true,sync_state:'not_synced'};
 mocks.get.mockImplementation((p:string)=>Promise.resolve(p.endsWith('catalog/')?{enabled:true,items:[complete,pending]}:[]));
 const w=mount(View,{attachTo:document.body,global:{plugins:[Antd]}});await flushPromises();
 expect(w.text()).toContain('等待同步的雨崩');expect(w.text()).not.toContain('已经同步的九寨沟');
 w.findAllComponents(Select)[1]!.vm.$emit('update:value','synced');await flushPromises();
 expect(w.text()).toContain('已经同步的九寨沟');expect(w.text()).not.toContain('等待同步的雨崩');
 expect(w.find('tbody input[type="checkbox"]').attributes('disabled')).toBeDefined();w.unmount();
 });

});
