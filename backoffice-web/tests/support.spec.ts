import {describe,it,expect,vi,beforeEach,afterEach} from 'vitest';
import {mount,flushPromises,type VueWrapper} from '@vue/test-utils';
import {createRouter,createMemoryHistory} from 'vue-router';
import Antd from 'ant-design-vue';
import SupportTickets from '../src/views/SupportTicketsView.vue';
import {sendSupportMutation} from '../src/api/modules/support';
const mocks=vi.hoisted(()=>({get:vi.fn(),post:vi.fn(),patch:vi.fn()}));
vi.mock('../src/api/http',()=>({default:mocks}));
vi.mock('../src/stores/auth',()=>({useAuthStore:()=>({user:{id:7},hasPermission:(p:string)=>p==='support_center.view_ticket'})}));
const ticket=(id:string)=>({id,number:'FB'+id,title:'问题'+id,kind:'usage',status:'processing',revision:2,owner_id:12,assignee_id:7,assignee:'客服',contact:'***',source:'settings',priority:'normal',tags:[],environment:{version:'1.0'},allowed_actions:['reply','note'],public_sequence:1,user_unread:true,created_at:'2026-10-20T00:00:00Z',last_public_activity_at:'2026-10-20T00:00:00Z'});
const deferred=<T>()=>{let resolve!:(v:T)=>void;const promise=new Promise<T>(r=>resolve=r);return {promise,resolve};};
let wrapper:VueWrapper|undefined;
beforeEach(()=>{sessionStorage.clear();mocks.get.mockReset();mocks.post.mockReset();mocks.patch.mockReset();mocks.post.mockResolvedValue({});});
afterEach(()=>{wrapper?.unmount();wrapper=undefined;document.body.innerHTML='';});
async function page(){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:SupportTickets}]});await router.push('/');await router.isReady();wrapper=mount({template:"<router-view />"},{attachTo:document.body,global:{plugins:[Antd,router]}});await flushPromises();return wrapper;}
describe('support mutation recovery',()=>{
 it('retries original payload and key after response loss even when revision changed',async()=>{mocks.post.mockRejectedValueOnce(Error('timeout'));await expect(sendSupportMutation(7,'A','messages',2,{body:'请重试',visibility:'public'})).rejects.toThrow('timeout');const first=mocks.post.mock.calls[0]![1];mocks.post.mockResolvedValueOnce(ticket('A'));await sendSupportMutation(7,'A','messages',9,{body:'请重试',visibility:'public'});expect(mocks.post.mock.calls[1]![1]).toEqual(first);expect(sessionStorage.length).toBe(0);});
 it('releases rejected conflict before a deliberate retry on refreshed revision',async()=>{mocks.post.mockRejectedValueOnce(Object.assign(Error('conflict'),{status:409}));await expect(sendSupportMutation(7,'A','actions',2,{action:'resolve',body:'已处理'})).rejects.toThrow();const first=mocks.post.mock.calls[0]![1];await sendSupportMutation(7,'A','actions',3,{action:'resolve',body:'已处理'});expect(mocks.post.mock.calls[1]![1].revision).toBe(3);expect(mocks.post.mock.calls[1]![1].client_request_id).not.toBe(first.client_request_id);});
});
describe('support workbench',()=>{
 it('ignores a late detail response after selecting a different ticket',async()=>{const late=deferred<unknown>();mocks.get.mockImplementation((path:string)=>{if(path.endsWith('/tickets/'))return Promise.resolve({results:[ticket('A'),ticket('B')],next_cursor:null});if(path.endsWith('/tickets/A/'))return late.promise;if(path.endsWith('/tickets/B/'))return Promise.resolve(ticket('B'));return Promise.resolve({results:[],next_cursor:null});});const w=await page();const buttons=w.findAll('button').filter(b=>b.text().replace(/\s/g,'')==='查看');await buttons[0]!.trigger('click');await buttons[1]!.trigger('click');await flushPromises();late.resolve(ticket('A'));await flushPromises();expect(document.body.textContent).toContain('FBB · 问题B');expect(document.body.textContent).not.toContain('FBA · 问题A');});
 it('marks only the fetched public message sequence as read',async()=>{mocks.get.mockImplementation((path:string)=>{if(path.endsWith('/tickets/'))return Promise.resolve({results:[{...ticket('A'),public_sequence:99}],next_cursor:null});if(path.endsWith('/tickets/A/'))return Promise.resolve({...ticket('A'),public_sequence:99});return Promise.resolve({results:[{id:'m1',body:'已答复',author_type:'staff',visibility:'public',sequence:4,attachments:[],created_at:'now',redacted:false}],next_cursor:'50'});});const w=await page();await w.findAll('button').find(b=>b.text().replace(/\s/g,'')==='查看')!.trigger('click');await flushPromises();expect(mocks.post).toHaveBeenCalledWith('/api/admin/v1/support/tickets/A/read/',{through_sequence:4});});
});
