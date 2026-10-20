import {describe,it,expect,vi,beforeEach,afterEach} from 'vitest';
import {mount,flushPromises,type VueWrapper} from '@vue/test-utils';
import Antd from 'ant-design-vue';
import Panel from '../src/views/PresetSearchMetadataPanel.vue';
const api=vi.hoisted(()=>({get:vi.fn(),put:vi.fn(),post:vi.fn(),patch:vi.fn()}));
vi.mock('../src/api/http',()=>({default:api}));
const unit=()=>({id:'garden',kind:'spread',title:'园林漫游',position:0,leftPageID:'left',rightPageID:'right',pairingSource:'explicit',searchEnabled:true,locationMode:'explicit',locationIDs:['suzhou'],tagIDs:['garden-theme'],searchKeywords:['假山']});
let wrapper:VueWrapper|undefined;
beforeEach(()=>{
 api.get.mockReset();api.post.mockReset();api.put.mockReset();
 api.get.mockImplementation(async(path:string)=>path.endsWith('tags/')?[{id:'garden-theme',dimension:'theme',name:'园林',aliases:[],active:true,parent:null},{id:'suzhou',dimension:'location',name:'苏州',aliases:[],active:true,parent:null}]:({revision:7,manifest:{schemaVersion:2,readingUnits:[unit()],metadata:{locationScope:'mixed',defaultLocationIDs:[]},pageMetadata:{left:{contentRole:'content'},right:{contentRole:'content'}}},pages:[{id:'left',title:'左页',thumbnail:'left.jpg'},{id:'right',title:'右页',thumbnail:'right.jpg'}]}));
 api.put.mockResolvedValue({revision:8});api.post.mockImplementation(async(path:string)=>path.endsWith('publish/')?{revision:9,searchable_spread_count:1}:{total:1,entries:[{id:'garden',title:'园林漫游',matched_fields:[{term:'园林',field:'theme',source:'explicit'}]}]});
});
afterEach(()=>{wrapper?.unmount();document.body.innerHTML=''});
function button(text:string){return wrapper!.findAll('button').find(b=>b.text()===text)!}
async function open(){wrapper=mount(Panel,{props:{templateId:'book'},global:{plugins:[Antd]},attachTo:document.body});await flushPromises();await vi.waitFor(()=>expect(button('保存并发布').attributes('disabled')).toBeUndefined());return wrapper}
describe('跨页搜索后台维护',()=>{
 it('编辑指定跨页保存草稿，不自动发布',async()=>{
  const w=await open();expect(w.findAll('.pair img')).toHaveLength(2);
  const title=w.findAll('input').find(i=>(i.element as HTMLInputElement).value==='园林漫游')!;
  await title.setValue('留园 · 窗内窗外');await button('保存草稿').trigger('click');await flushPromises();
  expect(api.put).toHaveBeenCalledTimes(1);const [path,payload]=api.put.mock.calls[0]!;
  expect(path).toContain('templates/book/reading-units/');expect(payload.revision).toBe(7);
  expect(payload.readingUnits[0].title).toBe('留园 · 窗内窗外');expect(payload.readingUnits[0].tagIDs).toEqual(['garden-theme']);
  expect(api.post).not.toHaveBeenCalled();
 });
 it('发布前试搜保存草稿并返回命中依据',async()=>{
  const w=await open();const title=w.findAll('input').find(i=>(i.element as HTMLInputElement).value==='园林漫游')!;
  await title.setValue('园林记录');await button('保存草稿并试搜').trigger('click');await flushPromises();
  expect(api.put).toHaveBeenCalledTimes(1);expect(api.post.mock.calls[0]?.[0]).toContain('search-preview/');
  expect(api.post.mock.calls[0]?.[1].revision).toBe(8);expect(w.text()).toContain('theme / explicit');
 });
 it('发布先保存最新元数据，并沿用保存后的 revision',async()=>{
  await open();await button('保存并发布').trigger('click');await flushPromises();
  expect(api.put).toHaveBeenCalledTimes(1);expect(api.post).toHaveBeenCalledWith(expect.stringContaining('templates/book/publish/'),{revision:8});
 });
});
