<script setup lang="ts">
import {ref,computed,onMounted,onBeforeUnmount,watch} from 'vue';
import {onBeforeRouteLeave,onBeforeRouteUpdate,useRoute,useRouter} from 'vue-router';
import {Modal,message} from 'ant-design-vue';
import type {FormInstance} from 'ant-design-vue';
import http from '../api/http';
import BatchPricingModal from '../components/billing/BatchPricingModal.vue';
import BillingSalesControl from './BillingSalesControl.vue';
import {useAuthStore} from '../stores/auth';
import {kinds,modes,kindLabel,policyLabel,formatDate,policyFromOffer,normalizePolicy,rights} from '../features/billing/policy';
const auth=useAuthStore(),route=useRoute(),router=useRouter();
const base='/api/v1/billing/manage/content-offers/',catalog='/api/v1/billing/manage/content-catalog/';
const canEdit=computed(()=>auth.hasPermission('billing.change_pricing_draft')),canPublish=computed(()=>auth.hasPermission('billing.publish_pricing'));
const rows=ref<any[]>([]),total=ref(0),page=ref(1),pageSize=ref(20),loading=ref(false),error=ref(''),testMode=ref(false),notice=ref('');
const filters=ref({q:'',target_kind:'',status:'',access_mode:'',availability:''});let listSequence=0;
const selected=ref<any>(null),draft=ref<any>({}),baseline=ref(''),savedBody=ref<string|null>(null),draftHash=ref<string|null>(null),preview=ref<any>(null),stale=ref<any>(null),busy=ref(false),detailLoading=ref(false),detailError=ref(''),activeTab=ref('edit'),history=ref<any[]>([]),policyForm=ref<FormInstance>();let detailSequence=0;
const dirty=computed(()=>!!selected.value&&!detailLoading.value&&baseline.value!==JSON.stringify(normalizePolicy(draft.value)));
const unsaved=computed(()=>savedBody.value!==JSON.stringify(normalizePolicy(draft.value)));
const diamond=computed(()=>['diamond_only','pro_or_diamond'].includes(draft.value.access_mode));
const bundleOptions=ref<any[]>([]),bundleQuery=ref(''),bundlePage=ref(1),bundleTotal=ref(0),bundleBusy=ref(false);let bundleSequence=0;
const bundleName=(id:string)=>bundleOptions.value.find(x=>x.value===id)?.label||id;
const bundleIds=computed({get:()=>draft.value.bundled_grants?.map((g:any)=>g.target_id)||[],set:(ids:string[])=>draft.value.bundled_grants=ids.map(target_id=>({target_kind:'sticker_library',target_id}))});
const picker=ref(false),pickerRows=ref<any[]>([]),pickerTotal=ref(0),pickerPage=ref(1),pickerBusy=ref(false),pickerError=ref(''),pickerFilters=ref({q:'',target_kind:'',status:''});let pickerSequence=0;
const viewportWidth=ref(window.innerWidth);
function updateViewport(){viewportWidth.value=window.innerWidth;}
const columns=computed(()=>[{title:'内容',key:'content',width:260},{title:'当前生效策略',key:'policy',width:220},{title:'待发布变更',key:'draft',width:220},...(viewportWidth.value>1200?[{title:'最近修改',key:'updated',width:175}]:[]),{title:'操作',key:'action',fixed:'right' as const,width:150}]);
const batchOpen=ref(false),batchBusy=ref(false),batchRows=ref<any[]>([]);
const rowKey=(r:any)=>r.target_kind+':'+r.target_id;
const selectedKeys=computed(()=>batchRows.value.map(rowKey));
function selectRows(keys:(string|number)[],records:any[]){if(keys.length>100){message.warning('每次最多选择 100 项内容');return;}const existing=new Map([...batchRows.value,...records].map(r=>[rowKey(r),r]));batchRows.value=keys.map(k=>existing.get(String(k))).filter(Boolean);}
function toggleRow(row:any,checked:boolean){const keys=selectedKeys.value.filter(k=>k!==rowKey(row));if(checked)keys.push(rowKey(row));selectRows(keys,[row]);}
function clearBatch(){batchRows.value=[];}
function batchSaved(result:any){batchOpen.value=false;clearBatch();notice.value=`已保存 ${result.saved_count} 项草稿，跳过 ${result.skipped_count} 项。请筛选“有草稿”逐项校验并发布。`;void load();}
const rules={change_reason:[{required:true,whitespace:true,message:'请填写本次变更的原因'},{max:500,message:'最多 500 字'}],diamond_price:[{validator:async(_:unknown,v:unknown)=>{if(typeof v!=='number'||!Number.isInteger(v)||v<1||v>1000000)throw Error('请输入 1 至 1000000 的整数钻石价格');}}]};
async function load(){const seq=++listSequence;loading.value=true;error.value='';try{const r:any=await http.get(catalog,{params:{...filters.value,page:page.value,page_size:pageSize.value}});if(seq!==listSequence)return;rows.value=r.items;total.value=r.total;page.value=r.page;testMode.value=r.test_policy_changes_enabled===true;}catch(e:any){if(seq===listSequence){error.value=e.message;rows.value=[];total.value=0;}}finally{if(seq===listSequence)loading.value=false;}}
function search(){clearBatch();page.value=1;void load();}function reset(){filters.value={q:'',target_kind:'',status:'',access_mode:'',availability:''};search();}
function pagination(p:any){page.value=p.current;pageSize.value=p.pageSize;void load();}
async function loadPicker(){const seq=++pickerSequence;pickerBusy.value=true;pickerError.value='';try{const r:any=await http.get(catalog,{params:{...pickerFilters.value,page:pickerPage.value,page_size:8}});if(seq===pickerSequence){pickerRows.value=r.items;pickerTotal.value=r.total;pickerPage.value=r.page;}}catch(e:any){if(seq===pickerSequence){pickerError.value=e.message;pickerRows.value=[];pickerTotal.value=0;}}finally{if(seq===pickerSequence)pickerBusy.value=false;}}
function searchPicker(){pickerPage.value=1;void loadPicker();}function openPicker(){picker.value=true;pickerFilters.value={q:'',target_kind:'',status:''};searchPicker();}
async function run(fn:()=>Promise<void>){if(busy.value)return;busy.value=true;detailError.value='';try{await fn();}catch(e:any){detailError.value=e.message;}finally{busy.value=false;}}
function confirmLeave(){if(!dirty.value)return Promise.resolve(true);return new Promise<boolean>(resolve=>Modal.confirm({title:'有尚未保存的修改',content:'离开将丢弃本次未保存输入；已保存草稿仍会保留。',okText:'放弃输入并离开',cancelText:'继续编辑',onOk:()=>resolve(true),onCancel:()=>resolve(false)}));}
async function close(){if(busy.value)return;if(await confirmLeave()){detailSequence++;selected.value=null;}}
async function edit(row:any,tab='edit'){
 if(!(await confirmLeave()))return;
 const seq=++detailSequence;selected.value=row;draft.value={};detailLoading.value=true;detailError.value='';activeTab.value=tab;preview.value=null;stale.value=null;history.value=[];baseline.value='';
 try{
  let offer=row;
  if(!offer.id){if(!canEdit.value)throw Error('此内容尚未配置策略，请联系具有草稿编辑权限的管理员。');offer=await http.post(base,{target_kind:row.target_kind,target_id:row.target_id});}
  const r:any=await http.get(`${base}${offer.id}/draft/`);if(seq!==detailSequence)return;
  selected.value={...row,...r.offer,title:row.title||r.offer?.title};stale.value=r.stale_body;draft.value=r.draft??policyFromOffer(r.offer??offer);draftHash.value=r.draft_hash??null;bundleOptions.value=r.bundle_options||[];
  baseline.value=JSON.stringify(normalizePolicy(draft.value));savedBody.value=r.draft?baseline.value:null;
  if(tab==='history')await loadHistory();
 }catch(e:any){if(seq===detailSequence)detailError.value=e.message;}finally{if(seq===detailSequence)detailLoading.value=false;}
}
async function choose(row:any){picker.value=false;await edit(row);}
async function loadHistory(){if(!selected.value?.id)return;const id=selected.value.id;try{const r:any=await http.get(`${base}${id}/history/`);if(selected.value?.id===id)history.value=r.items;}catch(e:any){detailError.value=e.message;}}
async function save(){if(!canEdit.value||busy.value)return;try{await policyForm.value?.validate();}catch{return;}
 await run(async()=>{const r:any=await http.patch(`${base}${selected.value.id}/draft/`,{...normalizePolicy(draft.value),expected_draft_hash:draftHash.value});draft.value=r.draft;draftHash.value=r.draft_hash;baseline.value=JSON.stringify(normalizePolicy(draft.value));savedBody.value=baseline.value;stale.value=null;preview.value=null;message.success('草稿已保存，线上策略尚未变化');await load();});}
async function inspect(){if(unsaved.value||busy.value)return;await run(async()=>{const r:any=await http.post(`${base}${selected.value.id}/publish-preview/`);if(r.draft_hash!==draftHash.value){throw Error('草稿已被其他操作员修改，请重新加载后检查。');}preview.value=r;});}
async function publish(){if(!canPublish.value||unsaved.value||!preview.value?.can_publish)return;await run(async()=>{const title=selected.value.title;const r:any=await http.post(`${base}${selected.value.id}/publish/`,{expected_draft_hash:preview.value.draft_hash});notice.value=`「${title}」策略 v${r.revision} 已发布 · ${formatDate(r.published_at)}`;baseline.value=JSON.stringify(normalizePolicy(draft.value));selected.value=null;preview.value=null;await load();});}
async function discard(){await run(async()=>{await http.delete(`${base}${selected.value.id}/draft/`,{data:{expected_draft_hash:draftHash.value}});baseline.value=JSON.stringify(normalizePolicy(draft.value));selected.value=null;message.success('草稿已放弃，线上策略保持原样');await load();});}
async function reloadDetail(){const row=selected.value;if(await confirmLeave()){baseline.value=JSON.stringify(normalizePolicy(draft.value));await edit(row);}}
async function loadBundles(q='',more=false){if(more&&bundleBusy.value)return;bundleQuery.value=q;if(!more)bundlePage.value=1;else bundlePage.value++;const seq=++bundleSequence;bundleBusy.value=true;try{const r:any=await http.get(catalog,{params:{q,target_kind:'sticker_library',availability:'available',page:bundlePage.value,page_size:20}});if(seq!==bundleSequence)return;bundleTotal.value=r.total;const choices=r.items.filter((x:any)=>x.id&&x.revision>0).map((x:any)=>({value:x.target_id,label:x.title}));const retained=bundleOptions.value.filter(x=>bundleIds.value.includes(x.value));bundleOptions.value=[...new Map([...(more?bundleOptions.value:retained),...choices].map(x=>[x.value,x])).values()];}catch(e:any){detailError.value=e.message;}finally{if(seq===bundleSequence)bundleBusy.value=false;}}
function beforeUnload(e:BeforeUnloadEvent){if(dirty.value||batchOpen.value){e.preventDefault();e.returnValue='';}}
async function fromRoute(){if(route?.path!=='/billing'||!route.query.target_id||!route.query.target_kind)return;try{const r:any=await http.get(catalog,{params:{q:String(route.query.target_id),target_kind:String(route.query.target_kind)}});if(r.items[0])await edit(r.items[0]);else message.warning('未找到可配置的公共内容');}catch(e:any){error.value=e.message;}}
async function leavePage(){if(busy.value||batchBusy.value)return false;if(batchOpen.value){message.info('请先完成或关闭批量配置窗口');return false;}const allowed=await confirmLeave();if(allowed){detailSequence++;selected.value=null;}return allowed;}
onBeforeRouteLeave(leavePage);onBeforeRouteUpdate(leavePage);
watch(()=>route?.fullPath,()=>{void fromRoute();});
onMounted(()=>{void load();void fromRoute();window.addEventListener('beforeunload',beforeUnload);window.addEventListener('resize',updateViewport);});
onBeforeUnmount(()=>{listSequence++;detailSequence++;pickerSequence++;bundleSequence++;window.removeEventListener('beforeunload',beforeUnload);window.removeEventListener('resize',updateViewport);});
</script>
<template>
<section class="billing-page">
 <header class="page-heading"><div><div class="eyebrow">内容运营</div><h1>内容定价与使用权益</h1><p>管理模板、贴纸与字体的使用方式。草稿保存后，校验影响再发布。</p></div><a-button v-if="canEdit" type="primary" size="large" @click="openPicker">新增内容策略</a-button></header>
 <BillingSalesControl @changed="preview=null;load()" />
 <div class="related"><router-link v-if="auth.hasPermission('billing.view_transactions')" to="/billing/transactions">交易与异常核查 ↗</router-link><router-link v-if="canPublish" to="/diary-customizations/packages">数字定制套餐 ↗</router-link></div>
 <a-alert v-if="notice" type="success" :message="notice" show-icon closable @close="notice=''"/>
 <a-alert v-if="testMode" type="warning" message="本地测试配置：允许调整已发布免费 / Pro 范围。此能力不代表生产环境已开放。" show-icon/>
 <a-alert v-if="error" type="error" :message="error" show-icon><template #action><a-button @click="load">重试</a-button></template></a-alert>
 <div class="filter-panel">
  <a-input-search v-model:value="filters.q" class="search" enter-button="搜索" placeholder="搜索内容名称或完整内容 ID" allow-clear @search="search"/>
  <a-select v-model:value="filters.target_kind" aria-label="筛选内容类型" :options="[{value:'',label:'全部内容类型'},...kinds]" @change="search"/>
  <a-select v-model:value="filters.status" aria-label="筛选策略状态" :options="[{value:'',label:'全部策略状态'},{value:'unconfigured',label:'待配置'},{value:'draft',label:'有待发布草稿'},{value:'blocked',label:'草稿发布受阻'},{value:'active',label:'已生效，无草稿'}]" @change="search"/>
  <a-select v-model:value="filters.access_mode" aria-label="筛选使用权益" :options="[{value:'',label:'全部使用权益'},...modes]" @change="search"/>
  <a-select v-model:value="filters.availability" aria-label="筛选内容状态" :options="[{value:'',label:'全部内容状态'},{value:'available',label:'内容可交付'},{value:'unavailable',label:'内容不可交付'}]" @change="search"/>
  <a-button @click="reset">重置</a-button><a-button :loading="loading" @click="load">刷新</a-button>
 </div>
 <div class="quick-filters" aria-label="常用策略查询"><a-radio-group v-model:value="filters.status" button-style="solid" @change="search"><a-radio-button value="">全部内容</a-radio-button><a-radio-button value="unconfigured">待配置</a-radio-button><a-radio-button value="draft">有草稿</a-radio-button><a-radio-button value="blocked">发布受阻</a-radio-button></a-radio-group></div>
 <div v-if="canEdit" class="batch-toolbar"><div><strong>批量配置</strong><span class="muted">已选择 {{batchRows.length}} 项 / 最多 100 项，可跨页选择；更改查询会清空选择。</span></div><a-space wrap><a-button :disabled="!batchRows.length" @click="clearBatch">清空选择</a-button><a-button type="primary" :disabled="!batchRows.length||loading" @click="batchOpen=true">批量配置草稿<span v-if="batchRows.length">（{{batchRows.length}}）</span></a-button></a-space></div>
 <div class="list-caption"><strong>内容策略</strong><span>共 {{ total }} 项 · 包含尚未配置策略的公共内容</span></div>
 <a-table :row-selection="canEdit?{selectedRowKeys:selectedKeys,preserveSelectedRowKeys:true,onChange:selectRows}:undefined" class="desktop-table" :columns="columns" :data-source="rows" :row-key="(r:any)=>r.target_kind+':'+r.target_id" :loading="loading" :scroll="{x:viewportWidth>1200?1045:820}" :pagination="{current:page,pageSize,total,showSizeChanger:true,showTotal:(n:number)=>`共 ${n} 项`}" @change="pagination">
 <template #bodyCell="{column,record}">
  <template v-if="column.key==='content'"><div class="content-identity"><img v-if="record.cover_url" :src="record.cover_url" alt="内容封面"/><div v-else class="cover-placeholder">{{ record.target_kind==='font'?'Aa':'图' }}</div><div><strong>{{ record.title }}</strong><small>{{ kindLabel(record.target_kind) }}</small><small class="row-update">{{record.updated_by||'尚未配置'}} · {{formatDate(record.updated_at)}}</small></div></div><small :class="record.available?'muted':'warning'">{{ record.available?'内容可交付':record.content_state==='unpublished'?'内容尚未发布':'内容不可交付' }}</small></template>
  <template v-else-if="column.key==='policy'"><a-tag :color="record.revision?'blue':'default'">{{ record.revision?'已生效 · v'+record.revision:'待配置' }}</a-tag><p>{{ policyLabel(record) }}</p></template>
  <template v-else-if="column.key==='draft'"><template v-if="record.draft"><a-tag :color="record.blockers?.length?'red':'orange'">{{ record.stale_draft?'草稿已过期':record.blockers?.length?'发布受阻':'待发布草稿' }}</a-tag><small v-if="record.blockers?.length" class="warning">{{record.blockers[0].message}}</small><p>{{ policyLabel(record) }} → {{ policyLabel(record.draft) }}</p><small v-if="record.draft.change_reason">{{ record.draft.change_reason }}</small></template><span v-else class="muted">暂无待发布变更</span></template>
  <template v-else-if="column.key==='updated'">{{ record.updated_by||'—' }}<small>{{ formatDate(record.updated_at) }}</small></template>
  <template v-else-if="column.key==='action'"><div class="row-actions"><a-button type="link" :disabled="!record.id&&!canEdit" @click="edit(record)">{{ !canEdit?'查看策略':record.draft?'继续编辑':record.revision?'编辑策略':'配置策略' }}</a-button><a-button type="link" :disabled="!record.revision" @click="edit(record,'history')">版本历史</a-button></div></template>
 </template><template #emptyText><a-empty description="没有匹配的内容，试试调整筛选条件。"/></template></a-table>
 <div class="mobile-list"><a-spin :spinning="loading"><a-empty v-if="!rows.length" description="没有匹配的内容"/><article v-for="r in rows" :key="r.target_id" class="content-card"><a-checkbox v-if="canEdit" :checked="selectedKeys.includes(rowKey(r))" :aria-label="'选择 '+r.title" @change="(e:any)=>toggleRow(r,e.target.checked)">选择此内容</a-checkbox><div class="content-identity"><img v-if="r.cover_url" :src="r.cover_url" alt="内容封面"/><div v-else class="cover-placeholder">{{r.target_kind==='font'?'Aa':'图'}}</div><div><strong>{{ r.title }}</strong><small>{{ kindLabel(r.target_kind) }} · {{ r.available?'内容可交付':'内容不可交付' }}</small></div></div><p>线上：{{ policyLabel(r) }} <a-tag v-if="r.revision">v{{r.revision}}</a-tag></p><p v-if="r.draft" class="warning">{{ r.stale_draft?'过期草稿':r.blockers?.length?'发布受阻':'待发布' }}：{{policyLabel(r.draft)}}</p><small>{{r.updated_by||'尚未配置'}} · {{formatDate(r.updated_at)}}</small><a-space><a-button :disabled="!r.id&&!canEdit" @click="edit(r)">{{canEdit?(r.draft?'继续编辑':r.id?'编辑策略':'配置策略'):'查看策略'}}</a-button><a-button :disabled="!r.revision" @click="edit(r,'history')">版本历史</a-button></a-space></article></a-spin><a-pagination :current="page" :total="total" :page-size="pageSize" simple @change="(p:number)=>{page=p;load()}"/></div>
 <BatchPricingModal :open="batchOpen" :items="batchRows" @close="batchOpen=false" @saved="batchSaved" @busy="batchBusy=$event"/>
 <a-modal :open="picker" title="选择需要配置策略的内容" :width="800" :footer="null" @cancel="picker=false">
  <p class="muted">按名称查找并核对内容。已有策略可直接打开；尚未发布的内容也可先保存草稿。</p>
  <div class="filter-panel"><a-input-search v-model:value="pickerFilters.q" class="search" placeholder="内容名称 / 完整内容 ID" allow-clear @search="searchPicker"/><a-select v-model:value="pickerFilters.target_kind" aria-label="选择内容类型" :options="[{value:'',label:'全部类型'},...kinds]" @change="searchPicker"/><a-select v-model:value="pickerFilters.status" :options="[{value:'',label:'全部内容'},{value:'unconfigured',label:'仅待配置内容'}]" @change="searchPicker"/></div>
  <a-alert v-if="pickerError" type="error" :message="pickerError"/>
  <a-list :data-source="pickerRows" :loading="pickerBusy"><template #renderItem="{item}"><a-list-item><div class="content-identity"><img v-if="item.cover_url" :src="item.cover_url" alt="内容封面"/><div v-else class="cover-placeholder">{{item.target_kind==='font'?'Aa':'图'}}</div><div><strong>{{item.title}}</strong><small>{{kindLabel(item.target_kind)}} · {{item.available?'内容可交付':'内容尚不可交付'}}</small><small>{{policyLabel(item)}}</small></div></div><template #actions><a-button type="primary" @click="choose(item)">{{item.id?'查看现有策略':'选择并配置'}}</a-button></template></a-list-item></template></a-list>
  <a-pagination :current="pickerPage" :total="pickerTotal" :page-size="8" :show-size-changer="false" @change="(p:number)=>{pickerPage=p;loadPicker()}"/>
 </a-modal>
 <a-drawer :open="!!selected" :title="selected?.title||'内容策略'" width="min(760px, 100vw)" :mask-closable="!busy" :closable="!busy" @close="close">
  <a-spin :spinning="detailLoading"><a-alert v-if="detailError" type="error" :message="detailError" show-icon><template #action><a-button :disabled="busy" @click="reloadDetail">重新加载</a-button></template></a-alert>
  <template v-if="selected && !detailLoading && draft.access_mode">
  <div class="detail-meta"><a-tag>{{kindLabel(selected.target_kind)}}</a-tag><span>线上版本 {{selected.revision?'v'+selected.revision:'尚未发布'}}</span><a-button v-if="selected.content_path" type="link" @click="router.push(selected.content_path)">管理内容 ↗</a-button></div>
  <a-tabs v-model:active-key="activeTab" @change="(k:string)=>{if(k==='history')loadHistory()}"><a-tab-pane key="edit" :tab="canEdit?'编辑与发布':'策略详情'"/><a-tab-pane key="history" tab="版本历史"/></a-tabs>
  <template v-if="activeTab==='history'"><a-empty v-if="!history.length" description="尚无已发布版本"/><a-timeline><a-timeline-item v-for="h in history" :key="h.revision"><strong>v{{h.revision}} · {{policyLabel(h)}}</strong><small>{{h.published_by}} · {{formatDate(h.created_at)}}</small><p>{{h.change_reason||'历史版本未记录变更原因'}}</p><small>附赠 {{h.bundled_grants.length}} 个素材包 · 条款 {{h.terms_version}}</small></a-timeline-item></a-timeline></template>
  <template v-else>
   <a-alert v-if="stale" type="warning" show-icon message="旧草稿已过期，当前表单已加载最新线上策略。请对比后重新填写并保存。" :description="`旧草稿：${policyLabel(stale)}；原因：${stale.change_reason}；附赠 ${stale.bundled_grants?.length||0} 个素材包`"/>
   <a-button v-if="stale&&canEdit" :disabled="busy" style="margin-bottom:12px" @click="draft={...JSON.parse(JSON.stringify(stale)),expected_revision:selected.revision,change_reason:''}">载入旧草稿内容，基于最新版本重新编辑</a-button>
   <a-alert v-if="!canEdit" type="info" message="当前为只读模式；草稿由具有编辑权限的操作员修改。"/>
   <div class="compare"><div><small>当前生效</small><strong>{{policyLabel(selected)}}</strong><small>附赠 {{selected.bundled_grants?.length||0}} 个素材包</small><small v-for="g in selected.bundled_grants" :key="g.target_id">{{bundleName(g.target_id)}}</small><small>条款：{{selected.terms_version}}</small></div><div><small>{{dirty?'未保存修改':savedBody?'已保存草稿':'待配置草稿'}}</small><strong>{{policyLabel(draft)}}</strong><small>附赠 {{draft.bundled_grants?.length||0}} 个素材包</small><small v-for="g in draft.bundled_grants" :key="g.target_id">{{bundleName(g.target_id)}}</small><small>条款：{{draft.terms_version}}</small></div></div>
   <a-form ref="policyForm" :model="draft" :disabled="busy||!canEdit" layout="vertical">
    <a-form-item label="使用方式"><a-select v-model:value="draft.access_mode" :options="modes"/></a-form-item>
    <a-form-item v-if="diamond" label="永久解锁价格（钻石）" name="diamond_price" :rules="rules.diamond_price"><a-input-number v-model:value="draft.diamond_price" :min="1" :max="1000000" :precision="0" style="width:100%"/></a-form-item>
    <a-form-item v-if="selected.target_kind==='template'" label="永久解锁时附赠的贴纸 / 背景包"><a-select v-model:value="bundleIds" mode="multiple" show-search :filter-option="false" :options="bundleOptions" :loading="bundleBusy" placeholder="搜索已发布的素材包" @focus="loadBundles()" @search="(q:string)=>loadBundles(q)"/><a-button v-if="bundlePage*20<bundleTotal" type="link" :loading="bundleBusy" @click="loadBundles(bundleQuery,true)">加载更多素材包</a-button><small>最多 30 个；仅随钻石永久解锁授予附赠许可，修改时保留已有配置。</small></a-form-item>
    <a-form-item label="变更说明" name="change_reason" :rules="rules.change_reason"><a-textarea v-model:value="draft.change_reason" :maxlength="500" show-count :rows="3" placeholder="说明调整原因，例如：新增主题包，首次设置永久解锁价格"/></a-form-item>
   </a-form>
   <div class="rights"><strong>发布后，用户将获得什么</strong><div v-for="r in rights(draft.access_mode)" :key="r.user"><span>{{r.user}}</span><span>{{r.result}}</span></div><small>使用仍受内容可用状态影响；已拥有用户按原许可交付。</small></div>
   <a-space wrap class="draft-actions"><a-button v-if="canEdit" type="primary" :loading="busy" @click="save">保存草稿</a-button><a-button :disabled="unsaved||busy" @click="inspect">校验与查看影响</a-button><a-popconfirm v-if="canEdit&&draftHash" title="放弃已保存草稿及当前输入？线上策略不会变化。" @confirm="discard"><a-button danger :disabled="busy">放弃草稿</a-button></a-popconfirm></a-space>
   <p v-if="unsaved" class="muted">请先保存草稿，再校验与发布。</p><p v-if="!canPublish" class="muted">保存后，请具有“收费策略发布”权限的管理员打开此内容，校验并发布。</p>
   <section v-if="preview&&!unsaved" class="impact"><h3>发布前检查</h3><a-alert v-for="b in preview.blockers" :key="b.code+b.message" type="error" show-icon :message="b.message"><template #action><a-button v-if="b.destination&&b.destination!=='/billing'" type="link" @click="router.push(b.destination)">检查内容</a-button></template></a-alert><a-alert v-if="preview.can_publish" type="success" message="当前发布条件校验通过；提交时将再次检查版本和配置。" show-icon/><p>永久拥有用户：{{preview.owned_users}} 人 · 待处理订单：{{preview.pending_orders}} 笔</p><p v-for="w in preview.warnings" :key="w" class="muted">{{w}}</p><a-popconfirm :title="`确认发布「${selected.title}」的新策略？`" :description="`${policyLabel(selected)} → ${policyLabel(draft)}；附赠 ${selected.bundled_grants?.length||0} → ${draft.bundled_grants?.length||0} 个素材包。已永久解锁用户保留原许可。`" ok-text="确认发布" cancel-text="再检查一下" @confirm="publish"><a-button type="primary" :disabled="!canPublish||!preview.can_publish||busy" :loading="busy">发布已校验草稿</a-button></a-popconfirm></section>
  </template></template></a-spin>
 </a-drawer>
</section>
</template>
<style scoped>
.batch-toolbar{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 16px;background:#eff6ff;border:1px solid #dbeafe;border-radius:8px}.batch-toolbar .muted{display:block;margin-top:5px}.content-card>.ant-checkbox-wrapper{margin-bottom:12px}@media(max-width:800px){.batch-toolbar{align-items:flex-start;flex-direction:column}}
.billing-page{padding:24px;min-width:0;background:#fff;border-radius:12px}.page-heading{display:flex;justify-content:space-between;gap:20px;align-items:center}.eyebrow{font-size:12px;color:#64748b;letter-spacing:2px}h1{font-size:26px;margin:6px 0 10px}.page-heading p{color:#64748b;margin-bottom:0}.related{display:flex;gap:20px;margin:12px 0 16px}.filter-panel{display:flex;gap:10px;flex-wrap:wrap;padding:12px;background:#f6f8fb;border-radius:8px;margin:16px 0}.filter-panel .ant-select{min-width:145px;flex:1 1 145px}.search{flex:1 1 100%;max-width:none}.quick-filters{margin:16px 0}.quick-filters .ant-radio-group{display:flex;flex-wrap:wrap}.row-update{display:none}.list-caption{display:flex;justify-content:space-between;gap:12px;margin:20px 0 12px}.list-caption span,.muted,small{color:#64748b;font-size:12px}small{display:block;margin-top:6px;overflow-wrap:anywhere}.warning{color:#a65b00}.content-identity{display:flex;align-items:center;gap:12px}.content-identity img,.cover-placeholder{width:48px;height:56px;object-fit:cover;border-radius:6px;flex-shrink:0}.cover-placeholder{display:grid;place-items:center;background:#edf2f7;color:#65748a;font-size:20px}.row-actions{display:flex;flex-direction:column;align-items:flex-start}.row-actions .ant-btn{padding-left:0}.compare{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:18px 0}.compare>div{padding:16px;background:#f6f8fb;border:1px solid #e5eaf2;border-radius:8px}.compare strong{display:block;margin-top:8px}.rights{padding:16px;background:#f6f8fb;border-radius:8px}.rights>div{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:10px 0;border-bottom:1px solid #e5eaf2}.draft-actions{margin-top:24px}.impact{border-top:1px solid #e5eaf2;margin-top:24px;padding-top:20px}.mobile-list{display:none}.detail-meta{display:flex;align-items:center;flex-wrap:wrap;gap:10px}:deep(.ant-alert){margin:12px 0}:deep(.ant-table-cell){overflow-wrap:break-word}:deep(.ant-table-thead th){white-space:nowrap}.content-card{padding:18px;border:1px solid #e5eaf2;border-radius:8px;margin-bottom:12px}.content-card .ant-space{margin-top:12px}
@media(min-width:801px) and (max-width:1200px){.row-update{display:block}:deep(.ant-table-cell){padding:12px!important}}
@media(max-width:800px){.billing-page{padding:18px}.page-heading{align-items:flex-start;flex-direction:column}.page-heading .ant-btn{width:100%}h1{font-size:23px}.desktop-table{display:none}.mobile-list{display:block}.filter-panel .ant-select{flex:1;min-width:140px}.search{max-width:none;flex-basis:100%}.list-caption{flex-direction:column}.related{flex-wrap:wrap}.compare{grid-template-columns:1fr}.rights>div{grid-template-columns:1fr}.content-identity strong{overflow-wrap:anywhere}}
</style>
