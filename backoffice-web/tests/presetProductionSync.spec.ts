import {describe,it,expect,vi,beforeEach,afterEach} from 'vitest';
import {mount,flushPromises,type VueWrapper} from '@vue/test-utils';
import Antd from 'ant-design-vue';
import Sync from '../src/views/PresetProductionSync.vue';
const mocks=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}));
vi.mock('../src/api/http',()=>({default:mocks}));
let w:VueWrapper<any>;
const record={id:'pack',title:'上海旅行手帐',version:1,revision:2,has_draft_changes:true};
const ready={id:'task',state:'ready',commit_status:'not_committed',source_version:1,result:{target_fingerprint:'fingerprint',target_version:0,next_version:1,count:31,added:31,resource_count:67}};
beforeEach(()=>{mocks.get.mockReset();mocks.post.mockReset();mocks.get.mockImplementation((p:string)=>Promise.resolve(p.endsWith('options/')?{can_sync:true,enabled:true}:p.endsWith('sync-history/')?{items:[],total:0}:ready));});
afterEach(()=>{w?.unmount();document.body.innerHTML='';});
async function page(){w=mount(Sync,{attachTo:document.body,global:{plugins:[Antd]}});await flushPromises();}
function button(text:string){return Array.from(document.querySelectorAll('button')).find(b=>b.textContent?.replace(/\s/g,'')===text)!;}
describe('whole-book production sync',()=>{
 it('preflights and requires explicit confirmation before publishing',async()=>{
  mocks.post.mockResolvedValue(ready);await page();await w.vm.open(record);await flushPromises();
  expect(mocks.post).toHaveBeenCalledTimes(1);expect(document.body.textContent).toContain('未发布修改');expect(document.body.textContent).toContain('31');
  mocks.post.mockResolvedValue({...ready,state:'queued'});button('确认同步并发布').click();await flushPromises();
  expect(mocks.post).toHaveBeenLastCalledWith('/api/admin/v1/diary-presets/sync-tasks/task/confirm/',{preflight_token:'fingerprint'});
 });
 it('restores an existing task without starting another import',async()=>{
  mocks.get.mockImplementation((p:string)=>Promise.resolve(p.endsWith('options/')?{can_sync:true,enabled:true}:p.endsWith('sync-history/')?{items:[{...ready,state:'outcome_unknown'}],total:1}:{...ready,state:'outcome_unknown'}));
  await page();await w.vm.open(record);await flushPromises();expect(mocks.post).not.toHaveBeenCalled();expect(document.body.textContent).toContain('正在确认生产结果');
 });
 it('shows production conflicts without offering confirmation',async()=>{
  mocks.post.mockResolvedValue({...ready,state:'conflict',result:{message:'生产存在未发布草稿'}});
  mocks.get.mockImplementation((p:string)=>Promise.resolve(p.endsWith('options/')?{}:p.endsWith('sync-history/')?{items:[],total:0}:{...ready,state:'conflict',result:{message:'生产存在未发布草稿'}}));
  await page();await w.vm.open(record);await flushPromises();expect(document.body.textContent).toContain('生产存在未发布草稿');expect(button('确认同步并发布')).toBeUndefined();
 });
});
