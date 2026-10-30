import {afterEach,expect,it} from 'vitest';
import {mount,flushPromises,DOMWrapper} from '@vue/test-utils';
import Antd,{Modal} from 'ant-design-vue';
import View from '../src/components/billing/BatchPricingModal.vue';
import http from '../src/api/http';
let w:any;const original=http.defaults.adapter;
afterEach(()=>{w?.unmount();Modal.destroyAll();http.defaults.adapter=original;document.body.innerHTML='';});
async function setup(){const calls:any[]=[];http.defaults.adapter=async config=>{calls.push({url:config.url,data:JSON.parse(config.data)});return {config,status:200,statusText:'OK',headers:{},data:{preview_hash:'hash-1',save_count:1,skipped_count:1,items:[{target_kind:'template',target_id:'one',title:'主题一',previous:{access_mode:'pro_only'},body:{access_mode:'free',bundled_grants:[],terms_version:'v3'},blockers:[],skipped:false},{target_kind:'font',target_id:'two',title:'字体二',previous:{access_mode:'free'},blockers:[],skipped:true,skip_reason:'已有草稿，默认保留'}]}};};w=mount(View,{props:{open:false,items:[{target_kind:'template',target_id:'one'},{target_kind:'font',target_id:'two'}],canPublish:true},attachTo:document.body,global:{plugins:[Antd]}});await w.setProps({open:true});await flushPromises();return calls;}
async function click(text:string){const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.replace(/\s/g,'')===text);expect(b).toBeTruthy();await new DOMWrapper(b!).trigger('click');await flushPromises();}
it('previews explicit selection and defaults to preserving existing drafts',async()=>{const calls=await setup();await new DOMWrapper(document.querySelector('textarea')!).setValue('统一开放');await click('预览批量变更');expect(calls.length).toBe(1);expect(calls[0].url).toContain('/preview/');expect(calls[0].data.overwrite_drafts).toBe(false);expect(calls[0].data.items.length).toBe(2);expect(document.body.textContent).toContain('待处理 1 项 · 跳过 1 项');expect(document.body.textContent).toContain('已有草稿，默认保留');});
it('invalidates a preview when the batch reason is edited',async()=>{await setup();const reason=new DOMWrapper(document.querySelector('textarea')!);await reason.setValue('首次批量调整');await click('预览批量变更');expect(document.body.textContent).toContain('保存 1 项草稿');await reason.setValue('重新调整');await flushPromises();expect(document.body.textContent).not.toContain('保存 1 项草稿');expect(document.body.textContent).toContain('先预览');});

it('blocks publishing when a selected item is skipped',async()=>{await setup();await new DOMWrapper(document.querySelector('textarea')!).setValue('统一开放');await click('预览批量变更');const button=[...document.querySelectorAll('button')].find(b=>b.textContent?.includes('发布全部 2 项'));expect(button?.disabled).toBe(true);expect(document.body.textContent).toContain('存在已有草稿的内容');});
it('sends one batch publish request after confirmation',async()=>{
 const calls:any[]=[];
 http.defaults.adapter=async config=>{calls.push({url:config.url,data:JSON.parse(config.data)});const data=config.url?.endsWith('/publish/')?{published_count:1}:{preview_hash:'hash-2',save_count:1,skipped_count:0,items:[{target_kind:'template',target_id:'one',title:'主题一',previous:{access_mode:'pro_only'},body:{access_mode:'free',bundled_grants:[],terms_version:'v1'},blockers:[],skipped:false}]};return {config,status:200,statusText:'OK',headers:{},data};};
 w=mount(View,{props:{open:true,items:[{target_kind:'template',target_id:'one'}],canPublish:true},attachTo:document.body,global:{plugins:[Antd]}});await flushPromises();
 await new DOMWrapper(document.querySelector('textarea')!).setValue('统一开放');await click('预览批量变更');await click('发布全部1项');await flushPromises();await click('确认批量发布');
 expect(calls.map(c=>c.url)).toEqual(['/api/v1/billing/manage/batch-pricing/preview/','/api/v1/billing/manage/batch-pricing/publish/']);expect(calls[1].data.expected_preview_hash).toBe('hash-2');expect(w.emitted('saved')?.[0]?.[0]).toEqual({published_count:1});
});
