vi.mock('../src/stores/auth',()=>({useAuthStore:()=>({hasPermission:()=>true})}));
import {describe,it,expect,vi,beforeEach,afterEach} from 'vitest';
import {mount,flushPromises,type VueWrapper} from '@vue/test-utils';
import Antd,{Modal} from 'ant-design-vue';
import {rememberUpload,readUploads} from '../src/views/materialUploadTasks';
import MaterialCatalog from '../src/views/MaterialCatalogView.vue';
const mocks=vi.hoisted(()=>({get:vi.fn(),post:vi.fn(),patch:vi.fn(),prepare:vi.fn(),put:vi.fn()}));
vi.mock('../src/views/materialImageUpload',()=>({prepareMaterialImage:mocks.prepare,putImageToOSS:mocks.put}));
vi.mock('../src/api/http',()=>({default:mocks}));
const pack={id:'pack',title:'出游',type:'sticker',template_id:null,availability:'published',version:1,count:1,state_revision:2,active:true,sort_order:0};
const categories=[{kind:'illustration',title:'插画与装饰',subcategories:[{id:'object',title:'主题物件'}]}];
let wrapper:VueWrapper|undefined;
beforeEach(()=>{mocks.get.mockReset();mocks.post.mockReset();mocks.patch.mockReset();mocks.prepare.mockReset();mocks.put.mockReset();mocks.put.mockResolvedValue(undefined);mocks.post.mockResolvedValue({});localStorage.clear();});
afterEach(()=>{Modal.destroyAll();vi.restoreAllMocks();wrapper?.unmount();wrapper=undefined;document.body.innerHTML='';});
function setup(){mocks.get.mockImplementation((path:string)=>{
 if(path.endsWith('options/'))return Promise.resolve({user_id:42,can_edit:true,can_publish:true,can_takedown:true,uploads_enabled:false});
 if(path.endsWith('categories/'))return Promise.resolve(categories);
 if(path.endsWith('/draft/'))return Promise.resolve({content:{title:'出游',description:'',tags:[],cover:'cover',previews:['preview'],items:[{revision:1}]},revision:3,base_version:1,items:[],images:{}});
 return Promise.resolve([pack]);
});}
async function page(){wrapper=mount(MaterialCatalog,{attachTo:document.body,global:{plugins:[Antd]}});await flushPromises();return wrapper;}
describe('material management',()=>{
 it('loads the metadata endpoint and displays unquoted API failures',async()=>{
  mocks.get.mockImplementation((path:string)=>path.endsWith('categories/')?Promise.resolve(categories):Promise.reject(new Error('请求的接口不存在')));
  const w=await page();
  expect(mocks.get).toHaveBeenCalledWith('/api/v1/materials/manage/libraries/',{params:expect.objectContaining({q:'',paged:1,page:1,page_size:20})});
  expect(w.text()).toContain('请求的接口不存在');expect(w.text()).not.toContain('"请求的接口不存在"');
 });
 it('clears an old missing-endpoint error after a successful refresh',async()=>{
  mocks.get.mockImplementation((path:string)=>path.endsWith('categories/')?Promise.resolve(categories):Promise.reject(new Error('接口不存在')));
  const w=await page();expect(w.text()).toContain('接口不存在');setup();
  await w.findAll('button').find(b=>b.text().replace(/\s/g,'')==='刷新')!.trigger('click');await flushPromises();
  expect(w.text()).not.toContain('接口不存在');expect(w.text()).toContain('出游');
 });
 it('retains the publish idempotency key when the response is lost',async()=>{
  setup();const w=await page();
  await w.findAll('button').find(b=>b.text().replace(/\s/g,'')==='编辑')!.trigger('click');await flushPromises();
  mocks.post.mockImplementation((path:string)=>path.endsWith('/publish/')?Promise.reject(new Error('响应超时')):Promise.resolve({errors:[],warnings:[]}));
  const publishButton=()=>Array.from(document.querySelectorAll('button')).find(b=>b.textContent?.replace(/\s/g,'').includes('校验并发布'))!;
  const confirm=vi.spyOn(Modal,'confirm').mockImplementation(()=>({destroy:vi.fn(),update:vi.fn()}));
  publishButton().click();await flushPromises();
  await expect(confirm.mock.calls[0]![0].onOk!()).rejects.toThrow('响应超时');
  publishButton().click();await flushPromises();
  await expect(confirm.mock.calls[1]![0].onOk!()).rejects.toThrow('响应超时');
  const calls=mocks.post.mock.calls.filter(([path])=>String(path).endsWith('/publish/'));
  expect(calls).toHaveLength(2);expect(calls[0]![1]).toEqual(calls[1]![1]);
  expect(calls[0]![1]).toMatchObject({expected_draft_revision:3,expected_version:1});
 });
 it('saves only draft JSON and retains unsaved edits on a conflict',async()=>{
  setup();const w=await page();await w.findAll('button').find(b=>b.text().replace(/\s/g,'')==='编辑')!.trigger('click');await flushPromises();
  mocks.patch.mockRejectedValue(new Error('内容已更新，请重新加载后重试'));
  const save=Array.from(document.querySelectorAll('button')).find(b=>b.textContent?.replace(/\s/g,'').includes('保存草稿'))!;
  save.click();await flushPromises();
  expect(mocks.patch).toHaveBeenCalledWith('/api/v1/materials/manage/libraries/pack/draft/',expect.objectContaining({expected_draft_revision:3,content:expect.objectContaining({title:'出游'})}));
  expect(document.body.textContent).toContain('出游');expect(document.body.textContent).toContain('内容已更新');
 });
 it('blocks publishing incomplete drafts with actionable reasons',async()=>{
  setup();const original=mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation((path:string)=>path.endsWith('/draft/')?Promise.resolve({content:{title:'未完成',cover:null,previews:[],items:[]},revision:1,base_version:0,items:[],images:{},uploads_enabled:false}):original(path));
  const w=await page();await w.findAll('button').find(b=>b.text().replace(/\s/g,'')==='编辑')!.trigger('click');await flushPromises();
  const button=Array.from(document.querySelectorAll('button')).find(b=>b.textContent?.includes('校验并发布'))!;
  expect(button.disabled).toBe(true);expect(document.body.textContent).toContain('添加封面');expect(document.body.textContent).toContain('OSS 上传暂不可用');
 });
 it('updates a material revision in place before saving the draft',async()=>{
  setup();const original=mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation((path:string)=>path.endsWith('/draft/')?Promise.resolve({content:{title:'出游',cover:'c',previews:['p'],items:[{revision:1},{revision:2}]},revision:3,base_version:1,items:[{id:'a',revision:1,name:'旧图'},{id:'b',revision:2,name:'另一张'}],latest_items:[{id:'a',revision:5,name:'新图'}],images:{}}):original(path));
  mocks.patch.mockResolvedValue({revision:4});const w=await page();await w.findAll('button').find(b=>b.text().replace(/\s/g,'')==='编辑')!.trigger('click');await flushPromises();
  Array.from(document.querySelectorAll('button')).find(b=>b.textContent?.includes('更新版本'))!.click();await flushPromises();
  Array.from(document.querySelectorAll('button')).find(b=>b.textContent?.includes('保存草稿'))!.click();await flushPromises();
  expect(mocks.patch).toHaveBeenCalledWith(expect.any(String),expect.objectContaining({content:expect.objectContaining({items:[{revision:5},{revision:2}]})}));
 });
 it('requires explicit confirmation after validation before publishing',async()=>{
  setup();const w=await page();await w.findAll('button').find(b=>b.text().replace(/\s/g,'')==='编辑')!.trigger('click');await flushPromises();
  const confirm=vi.spyOn(Modal,'confirm').mockImplementation(()=>({destroy:vi.fn(),update:vi.fn()}));
  Array.from(document.querySelectorAll('button')).find(b=>b.textContent?.includes('校验并发布'))!.click();await flushPromises();
  expect(mocks.post).toHaveBeenCalledWith('/api/v1/materials/manage/libraries/pack/validate/',{expected_draft_revision:3});
  expect(mocks.post.mock.calls.some(([path])=>String(path).endsWith('/publish/'))).toBe(false);
  expect(confirm.mock.calls[0]![0].content).toContain('历史模板固定引用');
 });
 it('opens a newly created pack directly in its draft editor',async()=>{
  setup();mocks.post.mockResolvedValue({...pack,id:'new-pack'});const w=await page();
  await w.findAll('button').find(b=>b.text().replace(/\s/g,'')==='新建素材包')!.trigger('click');await flushPromises();
  const input=Array.from(document.querySelectorAll('input')).find(i=>i.placeholder==='例如：秋日旅行')!;
  input.value='春日出游';input.dispatchEvent(new Event('input',{bubbles:true}));await flushPromises();
  Array.from(document.querySelectorAll('.ant-modal-footer button')).at(-1)!.click();await flushPromises();
  expect(mocks.post).toHaveBeenCalledWith('/api/v1/materials/manage/libraries/',{title:'春日出游',type:'sticker',template_id:null});
  expect(mocks.get).toHaveBeenCalledWith('/api/v1/materials/manage/libraries/new-pack/draft/');
 });
 it('resumes verification of an OSS-uploaded file without uploading its bytes again',async()=>{
  setup();rememberUpload('42',{uploadID:'uploaded',libraryID:'pack',purpose:'sticker',name:'flower.png',createdAt:Date.now()});
  const original=mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation((path:string)=>path.endsWith('/uploads/uploaded/')?Promise.resolve({state:'verified',resource:{resource_id:'hash',url:'https://example.oss-cn-beijing.aliyuncs.com/a'}}):original(path));
  mocks.post.mockImplementation((path:string)=>path.endsWith('/complete/')?Promise.resolve({state:'verified',resource:{resource_id:'hash',url:'https://example.oss-cn-beijing.aliyuncs.com/a'}}):path.endsWith('manage/materials/')?Promise.resolve({id:'flower',revision:5,name:'花'}):Promise.resolve({}));
  mocks.patch.mockResolvedValue({revision:4});const w=await page();await w.findAll('button').find(b=>b.text().replace(/\s/g,'')==='编辑')!.trigger('click');await flushPromises();
  Array.from(document.querySelectorAll('button')).find(b=>b.textContent?.replace(/\s/g,'')==='重试')!.click();await flushPromises();
  expect(mocks.post.mock.calls.some(([path])=>String(path).endsWith('manage/uploads/'))).toBe(false);
  expect(mocks.post).toHaveBeenCalledWith('/api/v1/materials/manage/materials/',expect.objectContaining({upload_id:'uploaded'}));
  Array.from(document.querySelectorAll('button')).find(b=>b.textContent?.includes('保存草稿'))!.click();await flushPromises();
  expect(readUploads('42')).toEqual([]);
 });
 it('uploads browser-generated files directly and retries confirmation without reuploading',async()=>{
  setup();const original=mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async(path:string)=>{const result:any=await original(path);return path.endsWith('options/')||path.endsWith('/draft/')?{...result,uploads_enabled:true}:result});
  const metadata={original:{sha256:'original',byte_size:10},thumbnail:{sha256:'thumb',byte_size:5}};
  const prepared={metadata,original:new Blob(['original']),thumbnail:new Blob(['thumb'])};mocks.prepare.mockResolvedValue(prepared);
  let confirmations=0;
  mocks.post.mockImplementation((path:string)=>{
   if(path.endsWith('manage/uploads/'))return Promise.resolve({id:'new-upload',expires_at:new Date(Date.now()+3600000).toISOString(),uploads:{original:{url:'https://test.oss-cn-beijing.aliyuncs.com/original'},thumbnail:{url:'https://test.oss-cn-beijing.aliyuncs.com/thumbnail'}}});
   if(path.endsWith('/complete/'))return ++confirmations===1?Promise.reject(new Error('确认响应超时')):Promise.resolve({state:'verified',resource:{resource_id:'hash',url:'https://test.oss-cn-beijing.aliyuncs.com/image'}});
   if(path.endsWith('manage/materials/'))return Promise.resolve({id:'flower',revision:5,name:'花'});
   return Promise.resolve({});
  });
  const w=await page();await w.findAll('button').find(b=>b.text().replace(/\s/g,'')==='编辑')!.trigger('click');await flushPromises();
  const input=Array.from(document.querySelectorAll<HTMLInputElement>('input[type=file]')).find(i=>i.parentElement?.textContent?.includes('单张素材'))!;
  const file=new File(['original'],'flower.png',{type:'image/png'});Object.defineProperty(input,'files',{value:[file]});input.dispatchEvent(new Event('change',{bubbles:true}));await flushPromises();
  expect(mocks.prepare).toHaveBeenCalled();expect(mocks.put).toHaveBeenCalledTimes(2);
  expect(mocks.post).toHaveBeenCalledWith('/api/v1/materials/manage/uploads/',{purpose:'sticker',name:'flower.png',...metadata});
  expect(document.body.textContent).toContain('确认响应超时');
  Array.from(document.querySelectorAll('button')).find(b=>b.textContent?.replace(/\s/g,'')==='重试')!.click();await flushPromises();
  expect(mocks.put).toHaveBeenCalledTimes(2);expect(confirmations).toBe(2);
  expect(mocks.get.mock.calls.some(([path])=>String(path).includes('/uploads/'))).toBe(false);
 });
 it('rejects local image validation failures before requesting an upload URL',async()=>{
  setup();const original=mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async(path:string)=>{const result:any=await original(path);return path.endsWith('options/')||path.endsWith('/draft/')?{...result,uploads_enabled:true}:result});
  mocks.prepare.mockRejectedValue(new Error('贴纸必须包含实际透明像素'));const w=await page();
  await w.findAll('button').find(b=>b.text().replace(/\s/g,'')==='编辑')!.trigger('click');await flushPromises();
  const input=Array.from(document.querySelectorAll<HTMLInputElement>('input[type=file]')).find(i=>i.parentElement?.textContent?.includes('单张素材'))!;
  Object.defineProperty(input,'files',{value:[new File(['opaque'],'opaque.png',{type:'image/png'})]});input.dispatchEvent(new Event('change',{bubbles:true}));await flushPromises();
  expect(document.body.textContent).toContain('贴纸必须包含实际透明像素');expect(mocks.put).not.toHaveBeenCalled();
  expect(mocks.post.mock.calls.some(([path])=>String(path).endsWith('manage/uploads/'))).toBe(false);
 });
 it('ignores a late draft response after selecting another pack',async()=>{
  let resolveLate!:(value:unknown)=>void;const late=new Promise(resolve=>{resolveLate=resolve});
  const content=(title:string)=>({content:{title,description:'',tags:[],cover:null,previews:[],items:[]},revision:1,base_version:1,items:[],images:{}});
  mocks.get.mockImplementation((path:string)=>{
   if(path.endsWith('categories/'))return Promise.resolve(categories);
   if(path.endsWith('/A/draft/'))return late;
   if(path.endsWith('/B/draft/'))return Promise.resolve(content('B包新草稿'));
   return Promise.resolve([{...pack,id:'A',title:'A包'},{...pack,id:'B',title:'B包'}]);
  });
  const w=await page();const buttons=w.findAll('button').filter(b=>b.text().replace(/\s/g,'')==='编辑');
  await buttons[0]!.trigger('click');await buttons[1]!.trigger('click');await flushPromises();
  resolveLate(content('A包旧草稿'));await flushPromises();
  const values=Array.from(document.querySelectorAll('input')).map(i=>i.value);
  expect(values).toContain('B包新草稿');expect(values).not.toContain('A包旧草稿');
 });

});
