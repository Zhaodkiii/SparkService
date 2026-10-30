vi.mock('../src/stores/auth',()=>({useAuthStore:()=>({hasPermission:()=>true})}));
import {describe,it,expect,vi,beforeEach,afterEach} from 'vitest';
import {mount,flushPromises,type VueWrapper} from '@vue/test-utils';
import Antd from 'ant-design-vue';
import View from '../src/views/DiaryPresetsView.vue';
const api=vi.hoisted(()=>({get:vi.fn(),post:vi.fn(),put:vi.fn(),patch:vi.fn()}));
vi.mock('../src/api/http',()=>({default:api}));
vi.mock('vue-router',()=>({onBeforeRouteLeave:vi.fn()}));
vi.mock('../src/views/MaterialLibraryPanel.vue',()=>({default:{template:'<div />'}}));
vi.mock('../src/views/PresetSearchMetadataPanel.vue',()=>({default:{template:'<div />'}}));
let wrapper:VueWrapper|undefined;
let bookCount=1;
beforeEach(()=>{
 bookCount=1;api.get.mockReset();
 api.get.mockImplementation(async(path:string)=>{
 if(path.endsWith('series/'))return [{id:1,title:'城市漫游',slug:'city',active:true}];
 if(path.endsWith('statistics-metadata/'))return {started_at:'2026-10-27T02:00:00Z'};
 if(path.endsWith('templates/'))return [{id:'book',title:'大理手帐',page_count:17,series:1,position:0,active:true,current:1,revision:1,import_statistics:{book_count:bookCount,selection_count:1,selected_page_count:1,user_count:1}}];
 if(path.endsWith('pages/'))return {revision:1,pages:[{id:'3',title:'第 3 页',thumbnail:'x',import_count:1},{id:'4',title:'第 4 页',thumbnail:'x',import_count:0}],cover:'3'};
 if(path.endsWith('page-statistics/'))return {pages:[{id:'3',title:'第 3 页',count:1,removed:false},{id:'old',title:'历史页',count:2,removed:true}]};
 return [];
 });
});
afterEach(()=>{wrapper?.unmount();document.body.innerHTML='';});
async function open(){wrapper=mount(View,{global:{plugins:[Antd],stubs:{APageHeader:{template:'<div><slot /><slot name="extra" /></div>'}}},attachTo:document.body});await flushPromises();return wrapper;}
describe('独立添加统计',()=>{
 it('整本只显示整本次数，单页保留独立次数，刷新会重新加载',async()=>{
 const w=await open();expect(w.text()).toContain('整本添加');expect(w.text()).toContain('选页累计页数');expect(w.text()).toContain('此前未统计');
 await w.findAll('button').find(b=>b.text()==='管理单页')!.trigger('click');await flushPromises();
 expect(w.findAll('.pages-grid .muted').map(n=>n.text())).toEqual(['第 1 页 · 添加次数 1','第 2 页 · 添加次数 0']);
 expect(w.text()).not.toContain('随整本添加');
 bookCount=2;await w.findAll('button').find(b=>b.text().replace(/\s/g,'')==='刷新')!.trigger('click');await flushPromises();
 expect(api.get.mock.calls.filter(c=>String(c[0]).endsWith('templates/')).length).toBe(2);
 expect(w.findAll('.pages-grid .muted')[0]!.text()).toContain('添加次数 1');
 });
 it('缺少统计字段显示暂不可用',async()=>{
 const original=api.get.getMockImplementation()!;
 api.get.mockImplementation(async(path:string)=>{const data=await original(path);if(path.endsWith('templates/'))delete data[0].import_statistics;return data;});
 const w=await open();expect(w.text()).toContain('暂不可用');
 });
});
