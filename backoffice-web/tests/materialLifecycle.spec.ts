import {describe,it,expect,vi,beforeEach,afterEach} from 'vitest';
import {mount,flushPromises,type VueWrapper} from '@vue/test-utils';
import Antd,{Modal} from 'ant-design-vue';
import Links from '../src/views/MaterialBookLinks.vue';
import Lifecycle from '../src/views/MaterialLifecyclePanel.vue';
const api=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}));
vi.mock('../src/api/http',()=>({default:api}));
let wrapper:VueWrapper|undefined;
beforeEach(()=>{api.get.mockReset();api.post.mockReset();api.post.mockResolvedValue({items:[]});});
afterEach(()=>{Modal.destroyAll();wrapper?.unmount();wrapper=undefined;document.body.innerHTML='';});
const row={template_id:'book',template_title:'苏州手帐',type:'sticker',library_id:'pack',library_title:'春日贴纸',library_version:1,revision:4};
async function links(canEdit=true){
 api.get.mockImplementation((url:string)=>Promise.resolve(url.endsWith('/templates/')?{items:[]}:{items:[row],versions:[2,1]}));
 wrapper=mount(Links,{props:{library:{id:'pack',type:'sticker',version:2},canEdit},attachTo:document.body,global:{plugins:[Antd]}});
 await flushPromises();return wrapper;
}
const button=(text:string)=>Array.from(document.querySelectorAll('button')).find(b=>b.textContent?.replace(/\s/g,'')===text) as HTMLButtonElement;
async function deletion(links:any[]=[]){
 api.get.mockResolvedValue({id:'pack',title:'春日贴纸',state_revision:7,token:'preview-token',materials:31,versions:2,links,historical_bindings:[],resources:10,protected_bytes:100,cleanup_reason:'正式资源受保护'});
 wrapper=mount(Lifecycle,{props:{canDelete:true,canLink:true},attachTo:document.body,global:{plugins:[Antd]}});
 await (wrapper.vm as any).previewDelete({id:'pack'});await flushPromises();
}
async function enterName(){const input=document.querySelector('input[placeholder="输入完整素材包名称以确认"]') as HTMLInputElement;input.value='春日贴纸';input.dispatchEvent(new Event('input',{bubbles:true}));await flushPromises();}
describe('whole-book material lifecycle',()=>{
 it('requires confirmation and sends the displayed association revision on unlink',async()=>{
  const w=await links();const confirm=vi.spyOn(Modal,'confirm').mockImplementation(()=>({destroy:vi.fn(),update:vi.fn()}));
  await w.findAll('button').find(b=>b.text().replace(/\s/g,'')==='取消关联')!.trigger('click');expect(api.post).not.toHaveBeenCalled();
  await confirm.mock.calls[0]![0].onOk!();await flushPromises();
  expect(api.post).toHaveBeenCalledWith('/api/v1/materials/manage/templates/book/links/',{type:'sticker',linked:false,expected_revision:4});
 });
 it('explains fixed versions and hides mutation controls for readers',async()=>{
  const w=await links(false);expect(w.text()).toContain('下一次发布整本手帐');expect(w.text()).toContain('苏州手帐');
  expect(w.findAll('button').some(b=>b.text().includes('取消关联'))).toBe(false);
 });
 it('retains a conflict in the association editor',async()=>{
  const w=await links();api.post.mockRejectedValue(new Error('关联已更新，请刷新后重试'));
  const confirm=vi.spyOn(Modal,'confirm').mockImplementation(()=>({destroy:vi.fn(),update:vi.fn()}));
  await w.findAll('button').find(b=>b.text().replace(/\s/g,'')==='取消关联')!.trigger('click');
  await expect(confirm.mock.calls[0]![0].onOk!()).rejects.toThrow('关联已更新');await flushPromises();
  expect(w.text()).toContain('关联已更新');expect(w.text()).toContain('春日贴纸');
 });
 it('requires the exact name and submits the deletion preview token',async()=>{
  await deletion();expect(button('移入回收站').disabled).toBe(true);expect(api.post).not.toHaveBeenCalled();
  await enterName();expect(button('移入回收站').disabled).toBe(false);
  api.get.mockResolvedValue({items:[],page:1,total:0});button('移入回收站').click();await flushPromises();
  expect(api.post).toHaveBeenCalledWith('/api/v1/materials/manage/libraries/pack/recycle/',expect.objectContaining({operation:'delete',token:'preview-token',expected_state_revision:7,confirm_title:'春日贴纸'}));
 });
 it('blocks deletion while a whole book is still linked',async()=>{
  await deletion([row]);await enterName();expect(button('移入回收站').disabled).toBe(true);expect(document.body.textContent).toContain('取消全部关联');
 });
});
