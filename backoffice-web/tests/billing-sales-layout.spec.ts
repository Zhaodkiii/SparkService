import {afterEach,expect,it,vi} from 'vitest';
import {mount,flushPromises,DOMWrapper} from '@vue/test-utils';
import Antd,{Modal} from 'ant-design-vue';
import View from '../src/views/BillingSalesControl.vue';
import http from '../src/api/http';
vi.mock('../src/stores/auth',()=>({useAuthStore:()=>({user:{is_superuser:true}})}));
const original=http.defaults.adapter;let w:any;
afterEach(()=>{w?.unmount();Modal.destroyAll();http.defaults.adapter=original;document.body.innerHTML='';vi.restoreAllMocks();});
async function setup(){const calls:any[]=[];http.defaults.adapter=async config=>{calls.push(config);return {config,status:200,statusText:'OK',headers:{},data:{environment:'local-authoring',revision:2,diamond_redemption_enabled:true,membership_sales_enabled:true,updated_at:'2026-10-30T01:57:01Z',updated_by:'管理员'}};};w=mount(View,{attachTo:document.body,global:{plugins:[Antd]}});await flushPromises();return calls;}
it('shows saved status without placing editable switches in the content workspace',async()=>{await setup();expect(w.text()).toContain('本地内容编制环境');expect(w.text()).toContain('钻石兑换 已开放');expect(document.querySelector('[role="switch"]')).toBeNull();await w.find('button').trigger('click');await flushPromises();expect(document.body.textContent).toContain('此处修改不会更改生产环境');expect(document.querySelectorAll('[role="switch"]').length).toBe(2);});
it('keeps edits local and confirms discarding them',async()=>{const calls=await setup();await w.find('button').trigger('click');await flushPromises();await new DOMWrapper(document.querySelector('[role="switch"]')!).trigger('click');await flushPromises();expect(document.body.textContent).toContain('保存后才会生效');expect(calls.every(c=>c.method==='get')).toBe(true);const confirm=vi.spyOn(Modal,'confirm');await new DOMWrapper(document.querySelector('.ant-modal-close')!).trigger('click');expect(confirm).toHaveBeenCalledWith(expect.objectContaining({title:'放弃尚未保存的销售设置？'}));});
