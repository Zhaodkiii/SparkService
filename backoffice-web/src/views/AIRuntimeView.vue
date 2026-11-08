<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue';
import { message } from 'ant-design-vue';
import { useAuthStore } from '../stores/auth';
import { runtime, type Provider, type Slot, type Model, type State, type Draft, type Release, type TestRun } from '../api/modules/aiRuntime';
const auth = useAuthStore();
const can = (name: string) => auth.hasPermission('button:ai:runtime:' + name);
const names: Record<string, string> = {'diary.layout':'手帐规划与排版','diary.background.design':'背景主题分析','diary.background.generate':'背景图片生成','diary.background.review':'背景质量检查'};
const providers = ref<Provider[]>([]), slots = ref<Slot[]>([]), models = ref<Model[]>([]), releases = ref<Release[]>([]), tests = ref<TestRun[]>([]);
const state = ref<State>();
const draft = ref<Draft>({minimum_build: 1, scenes: {}});
const tab = ref('overview'), loading = ref(false), busy = ref(false), error = ref(''), dirty = ref(false);
const current = computed(() => releases.value.find(r => r.id === state.value?.current));
const providerName = (id: string) => providers.value.find(p => p.id === id)?.name || id;
const columns = (fields: string[]) => fields.map(f => ({title: ({name:'名称',host:'域名',provider:'供应商',model_id:'上游模型',adapter_id:'协议',enabled:'状态',active_version:'密钥版本',actions:'操作'} as Record<string,string>)[f] || f, key: f, dataIndex: f}));
async function load() {
  loading.value = true; error.value = '';
  try {
    const [s,p,k,m,r,t] = await Promise.all([runtime.get<State>('drafts/current/'), runtime.get<{items:Provider[]}>('providers/'), runtime.get<{items:Slot[]}>('credential-slots/'), runtime.get<{items:Model[]}>('models/'), runtime.get<{items:Release[]}>('releases/'), runtime.get<{items:TestRun[]}>('tests/')]);
    state.value=s; providers.value=p.items; slots.value=k.items; models.value=m.items; releases.value=r.items; tests.value=t.items;
    if (!dirty.value) draft.value = {minimum_build: s.draft.minimum_build || 1, scenes: structuredClone({'diary.layout':{model:'',credential_slot:'',parameters:{},timeout_seconds:180},...(s.draft.scenes || {})})};
  } catch(e) { error.value = e instanceof Error ? e.message : '读取失败，请重试'; }
  finally { loading.value=false; }
}
async function act(work: () => Promise<void>) {
  if (busy.value) return;
  busy.value=true;
  try { await work(); message.success('操作成功'); }
  catch(e) { message.error(e instanceof Error ? e.message : '操作失败'); }
  finally { busy.value=false; }
}
const catalogReason = ref('');
const editor = ref<'providers'|'models'|'credential-slots'|null>(null);
const form = ref({id:'',name:'',host:'ark.cn-beijing.volces.com',provider:'',model_id:'',adapter_id:'ark_responses_v1',endpoint:'https://ark.cn-beijing.volces.com/api/v3/responses',capabilities:['vision','tools','stream'],enabled:true});
function edit(kind: NonNullable<typeof editor.value>, row?: Provider|Slot|Model) {
  editor.value=kind; catalogReason.value='';
  form.value={id:'',name:'',host:'ark.cn-beijing.volces.com',provider:providers.value[0]?.id || '',model_id:'',adapter_id:'ark_responses_v1',endpoint:'https://ark.cn-beijing.volces.com/api/v3/responses',capabilities:['vision','tools','stream'],enabled:true,...row};
}
function saveCatalog() { void act(async () => {
  const kind=editor.value; if (!kind) return;
  const f=form.value;
  const data = kind==='providers' ? {name:f.name,host:f.host,enabled:f.enabled} : kind==='credential-slots' ? {name:f.name,provider:f.provider,enabled:f.enabled} : {name:f.name,provider:f.provider,model_id:f.model_id,adapter_id:f.adapter_id,endpoint:f.endpoint,capabilities:f.capabilities,enabled:f.enabled};
  if (!f.name.trim()) throw Error('请填写名称');
  if (f.id) await runtime.patch(kind+'/'+f.id+'/',{...data,reason:catalogReason.value}); else await runtime.post(kind+'/',data);
  editor.value=null; await load();
}); }
const keySlot = ref<Slot>(), secret=ref(''), keyReason=ref(''), keyVersions=ref<{version:number;suffix:string;created_at:string}[]>([]), selectedVersion=ref<number>(), keyTestRelease=ref<string>();
async function openKey(slot: Slot) { keySlot.value=slot;secret.value='';keyReason.value='';selectedVersion.value=undefined;keyTestRelease.value=undefined;keyVersions.value=(await runtime.get<{items:typeof keyVersions.value}>('credential-slots/'+slot.id+'/versions/')).items; }
function closeKey(){keySlot.value=undefined;secret.value='';keyReason.value='';}
function addKey() { void act(async()=>{ if (!keySlot.value || !secret.value || !keyReason.value.trim()) throw Error('请填写密钥和原因');
  const slot=keySlot.value;try {await runtime.post('credential-slots/'+slot.id+'/versions/',{secret:secret.value,reason:keyReason.value});} finally {secret.value='';}
  await openKey(slot);
}); }
function activate() { void act(async()=>{if(!keySlot.value || !selectedVersion.value || !keyReason.value.trim()) throw Error('请选择版本并填写原因');
  await runtime.post('credential-slots/'+keySlot.value.id+'/activate/',{version:selectedVersion.value,expected_version:keySlot.value.active_version,request_key:crypto.randomUUID(),reason:keyReason.value});closeKey();await load();
}); }
function testKey() { void act(async()=>{if(!keySlot.value || !selectedVersion.value) throw Error('请选择待测试的凭证版本');
  await runtime.post('tests/',{slot_id:keySlot.value.id,credential_version:selectedVersion.value,...(keyTestRelease.value?{release_id:keyTestRelease.value}:{})});await load();message.info('已排队测试所选配置绑定场景。');
}); }
function toggleScene(name:string, enabled:boolean) {
  dirty.value=true;
  if(enabled) draft.value.scenes[name]={model:'',credential_slot:'',parameters:{},timeout_seconds:180}; else delete draft.value.scenes[name];
}
function sceneModels(name:string) {return models.value.filter(m=>m.enabled && m.adapter_id===(name==='diary.background.generate'?'ark_images_v1':'ark_responses_v1'));}
function sceneSlots(name:string) {const model=models.value.find(m=>m.id===draft.value.scenes[name]?.model);return slots.value.filter(s=>s.enabled && s.provider===model?.provider);}
function chooseModel(name:string){draft.value.scenes[name]!.credential_slot='';dirty.value=true;}
function saveDraft(){void act(async()=>{if(!state.value)return;const result=await runtime.put<State>('drafts/current/',{expected_revision:state.value.revision,draft:draft.value});state.value=result;dirty.value=false;await load();});}
function discard(){dirty.value=false;void load();}
function runTest(release?:Release){void act(async()=>{if(dirty.value)throw Error('请先保存草稿');await runtime.post('tests/',release?{release_id:release.id}:{});await load();});}
const preview=ref<Release|'publish'|null>(null), reason=ref(''), publishKey=ref('');
function openPublish(target: Release|'publish'){if(dirty.value){message.warning('请先保存草稿');return;}preview.value=target;reason.value='';publishKey.value=crypto.randomUUID();}
function publish(){void act(async()=>{if(!state.value||!preview.value||!reason.value.trim())throw Error('请填写发布原因');
  const path=preview.value==='publish'?'releases/':'releases/'+preview.value.id+'/rollback/';
  await runtime.post(path,{request_key:publishKey.value,expected_channel_version:state.value.channel_version,expected_draft_revision:state.value.revision,reason:reason.value});preview.value=null;await load();
});}
function copyRelease(row:Release){
  const next:Draft={minimum_build:row.snapshot.minimum_build,scenes:{}};
  for(const [name,value] of Object.entries(row.snapshot.scenes)){
    const model=models.value.find(m=>m.model_id===value.model_id&&m.adapter_id===value.adapter_id&&m.endpoint===value.endpoint);
    next.scenes[name]={model:model?.id||'',credential_slot:value.credential_slot_id,parameters:structuredClone(value.parameters),timeout_seconds:180};
  }
  draft.value=next;dirty.value=true;tab.value='scenes';
}
const controlOpen=ref(false), controlEnabled=ref(true), disabledScenes=ref<string[]>([]), controlReason=ref('');
function openControl(){controlEnabled.value=state.value?.enabled??true;disabledScenes.value=[...(state.value?.disabled_scenes||[])];controlReason.value='';controlOpen.value=true;}
function saveControl(){void act(async()=>{if(!state.value||!controlReason.value.trim())throw Error('请填写原因');await runtime.patch('controls/',{expected_version:state.value.channel_version,enabled:controlEnabled.value,disabled_scenes:disabledScenes.value,reason:controlReason.value});controlOpen.value=false;await load();});}
const recordKind=ref('deliveries'), records=ref<Record<string,unknown>[]>([]), recordPage=ref(1), recordTotal=ref(0), taskFilter=ref('');
async function loadRecords(){try{const result=await runtime.get<{items:Record<string,unknown>[];pagination:{total:number}}>(recordKind.value+'/',{page:recordPage.value,task_id:taskFilter.value||undefined});records.value=result.items;recordTotal.value=result.pagination.total;}catch(e){message.error(e instanceof Error?e.message:'读取失败');}}
function exportRecords(){const blob=new Blob([JSON.stringify(records.value,null,2)],{type:'application/json'});const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download='ai-runtime-records.json';a.click();URL.revokeObjectURL(u);}
let timer:ReturnType<typeof setInterval>|undefined;
onMounted(()=>{void load();timer=setInterval(()=>{if(tests.value.some(t=>['queued','running'].includes(t.state)))void runtime.get<{items:TestRun[]}>('tests/').then(v=>tests.value=v.items).catch(()=>{});},5000);});
onBeforeUnmount(()=>{if(timer)clearInterval(timer);secret.value='';});
</script>

<template>
  <main class="runtime-page">
    <header><div><h1>AI 服务配置</h1><p>配置发布到客户端，由客户端直接调用供应商</p></div><a-space><a-tag :color="state?.enabled?'green':'red'">{{state?.enabled?'服务开启':'服务停用'}}</a-tag><a-tag>线上版本 {{current?.sequence ?? '未发布'}}</a-tag><a-button :loading="loading" @click="load">刷新</a-button><a-button v-if="can('control')" danger @click="openControl">服务控制</a-button></a-space></header>
    <a-alert v-if="error" :message="error" type="error" show-icon class="gap"/>
    <a-alert v-if="dirty" message="草稿有未保存修改。刷新保留本地编辑；发生版本冲突时请对照后重新加载。" type="info" class="gap"/>
    <a-tabs v-model:activeKey="tab">
      <a-tab-pane key="overview" tab="概览">
        <div class="cards"><a-card v-for="(label,name) in names" :key="name" :title="label"><template v-if="current?.snapshot.scenes[name]"><p>{{current.snapshot.scenes[name]!.model_id}}</p><a-tag>{{current.snapshot.scenes[name]!.adapter_id}}</a-tag><p>{{state?.disabled_scenes.includes(String(name))?'已紧急停用':'已发布'}}</p></template><a-empty v-else description="尚未发布" :image="undefined"/></a-card></div>
        <a-descriptions bordered :column="2" class="gap"><a-descriptions-item label="发布人">{{current?.actor_id??'—'}}</a-descriptions-item><a-descriptions-item label="发布时间">{{current?.created_at??'—'}}</a-descriptions-item><a-descriptions-item label="最低客户端构建">{{current?.snapshot.minimum_build??'—'}}</a-descriptions-item><a-descriptions-item label="草稿版本">{{state?.revision}}</a-descriptions-item><a-descriptions-item label="环境">当前管理后台连接的部署环境（凭证不跨环境共享）</a-descriptions-item></a-descriptions>
      </a-tab-pane>
      <a-tab-pane key="providers" tab="供应商与凭证">
        <a-space class="gap"><a-button v-if="can('edit')" type="primary" @click="edit('providers')">新增供应商</a-button><a-button v-if="can('credential')" @click="edit('credential-slots')">新增凭证槽位</a-button></a-space>
        <a-table :data-source="providers" :columns="columns(['name','host','enabled','actions'])" row-key="id" :pagination="{pageSize:25}"><template #bodyCell="{column,record}"><template v-if="column.key==='enabled'">{{record.enabled?'可用':'停用'}}</template><a-button v-if="column.key==='actions' && can('edit')" type="link" @click="edit('providers',record)">编辑</a-button></template></a-table>
        <h3>凭证槽位</h3><a-table :data-source="slots" :columns="columns(['name','provider','active_version','enabled','actions'])" row-key="id" :pagination="{pageSize:25}"><template #bodyCell="{column,record}"><template v-if="column.key==='provider'">{{providerName(record.provider)}}</template><template v-if="column.key==='enabled'">{{record.enabled?'可用':'停用'}}</template><a-space v-if="column.key==='actions' && can('credential')"><a-button type="link" @click="edit('credential-slots',record)">编辑</a-button><a-button type="link" @click="openKey(record).catch(e=>message.error(e.message))">管理密钥</a-button></a-space></template></a-table>
      </a-tab-pane>
      <a-tab-pane key="models" tab="模型目录"><a-button v-if="can('edit')" class="gap" type="primary" @click="edit('models')">新增模型</a-button><a-table :data-source="models" :columns="columns(['name','provider','model_id','adapter_id','enabled','actions'])" row-key="id" :pagination="{pageSize:25}"><template #bodyCell="{column,record}"><template v-if="column.key==='provider'">{{providerName(record.provider)}}</template><template v-if="column.key==='enabled'">{{record.enabled?'可用':'归档'}}</template><a-button v-if="column.key==='actions'&&can('edit')" type="link" @click="edit('models',record)">编辑</a-button></template></a-table></a-tab-pane>
      <a-tab-pane key="scenes" tab="场景配置">
        <a-space class="gap"><span>最低客户端构建</span><a-input-number v-model:value="draft.minimum_build" :min="1" :disabled="!can('edit')" @change="dirty=true"/><a-button v-if="can('edit')" :loading="busy" @click="saveDraft">保存草稿</a-button><a-popconfirm title="放弃未保存的修改并重新加载？" @confirm="discard"><a-button>重新加载</a-button></a-popconfirm><a-button v-if="can('test')" :loading="busy" @click="runTest()">测试全部场景（可能计费）</a-button><a-button v-if="can('publish')" type="primary" @click="openPublish('publish')">发布预览</a-button></a-space>
        <div class="cards"><a-card v-for="(label,name) in names" :key="name" :title="label"><template #extra><a-switch :checked="!!draft.scenes[name]" :disabled="!can('edit')||name==='diary.layout'" @change="(v: unknown)=>toggleScene(String(name),Boolean(v))"/></template>
          <a-form v-if="draft.scenes[name]" layout="vertical" :disabled="!can('edit')">
            <a-form-item label="模型"><a-select v-model:value="draft.scenes[name]!.model" :options="sceneModels(String(name)).map(m=>({value:m.id,label:m.name+' · '+m.model_id}))" @change="chooseModel(String(name))"/></a-form-item>
            <a-form-item label="凭证槽位"><a-select v-model:value="draft.scenes[name]!.credential_slot" :options="sceneSlots(String(name)).map(s=>({value:s.id,label:s.name+' · v'+s.active_version}))" @change="dirty=true"/></a-form-item>
            <a-form-item label="请求超时（秒）"><a-input-number v-model:value="draft.scenes[name]!.timeout_seconds" :min="10" :max="360" @change="dirty=true"/></a-form-item>
            <template v-if="name==='diary.background.generate'"><a-form-item label="图片尺寸"><a-select :value="draft.scenes[name]!.parameters.size as string|undefined" :options="['1K','2K','4K'].map(v=>({value:v,label:v}))" allow-clear @change="(v: unknown)=>{if(v)draft.scenes[name]!.parameters.size=v;else delete draft.scenes[name]!.parameters.size;dirty=true}"/></a-form-item><a-form-item label="水印"><a-switch :checked="draft.scenes[name]!.parameters.watermark as boolean|undefined" @change="(v: unknown)=>{draft.scenes[name]!.parameters.watermark=Boolean(v);dirty=true}"/></a-form-item></template>
            <template v-else><a-form-item label="输出上限（留空沿用客户端场景值）"><a-input-number :value="draft.scenes[name]!.parameters.max_output_tokens as number|undefined" :min="256" :max="32768" @change="(v: unknown)=>{if(v)draft.scenes[name]!.parameters.max_output_tokens=Number(v);else delete draft.scenes[name]!.parameters.max_output_tokens;dirty=true}"/></a-form-item><a-form-item label="思考模式"><a-select :value="(draft.scenes[name]!.parameters.thinking as {type:string}|undefined)?.type" allow-clear :options="[{value:'enabled',label:'开启'},{value:'disabled',label:'关闭'}]" @change="(v: unknown)=>{if(v)draft.scenes[name]!.parameters.thinking={type:v};else delete draft.scenes[name]!.parameters.thinking;dirty=true}"/></a-form-item><a-form-item label="推理强度"><a-select :value="(draft.scenes[name]!.parameters.reasoning as {effort:string}|undefined)?.effort" allow-clear :options="['low','medium','high'].map(v=>({value:v,label:v}))" @change="(v: unknown)=>{if(v)draft.scenes[name]!.parameters.reasoning={effort:v};else delete draft.scenes[name]!.parameters.reasoning;dirty=true}"/></a-form-item></template>
          </a-form><a-empty v-else description="场景未启用"/>
        </a-card></div>
      </a-tab-pane>
      <a-tab-pane key="releases" tab="发布历史"><a-list :data-source="releases" :pagination="{pageSize:10}"><template #renderItem="{item}"><a-list-item><a-list-item-meta :title="'版本 '+item.sequence+(item.id===state?.current?' · 当前生效':'')" :description="item.created_at+' · '+item.reason"/><a-space><a-button v-if="can('edit')" @click="copyRelease(item)">复制为草稿</a-button><a-button v-if="can('test')" @click="runTest(item)">测试</a-button><a-button v-if="can('publish')" @click="openPublish(item)">详情 / 回滚</a-button></a-space></a-list-item></template></a-list></a-tab-pane>
      <a-tab-pane key="diagnostics" tab="诊断与审计">
        <h3>合成素材测试</h3><a-alert message="测试可能产生供应商费用。后台测试通过不代表所有客户端网络可达。" type="info" class="gap"/><a-table :data-source="tests" :columns="[{title:'时间',dataIndex:'created_at'},{title:'状态',dataIndex:'state'},{title:'结果',key:'results'}]" row-key="id" :pagination="{pageSize:10}"><template #bodyCell="{column,record}"><pre v-if="column.key==='results'">{{JSON.stringify(record.results,null,2)}}</pre></template></a-table>
        <template v-if="can('audit')"><a-space class="gap"><a-select v-model:value="recordKind" :options="[{value:'deliveries',label:'配置下发'},{value:'events',label:'客户端自报事件'},{value:'audits',label:'操作审计'}]"/><a-input v-model:value="taskFilter" placeholder="任务 UUID（审计不适用）"/><a-button @click="recordPage=1;loadRecords()">查询</a-button><a-button @click="exportRecords">导出当前页（脱敏）</a-button></a-space><a-list :data-source="records"><template #renderItem="{item}"><a-list-item><pre>{{JSON.stringify(item,null,2)}}</pre></a-list-item></template></a-list><a-pagination v-model:current="recordPage" :total="recordTotal" :page-size="25" @change="loadRecords"/></template>
      </a-tab-pane>
    </a-tabs>
    <a-drawer :open="!!editor" :title="form.id?'编辑配置':'新增配置'" :width="520" @close="editor=null"><a-form layout="vertical"><a-form-item label="名称"><a-input v-model:value="form.name" :maxlength="100"/></a-form-item><a-form-item v-if="editor==='providers'" label="部署白名单域名"><a-input v-model:value="form.host" :disabled="!!form.id"/></a-form-item><a-form-item v-else label="供应商"><a-select v-model:value="form.provider" :disabled="!!form.id" :options="providers.map(p=>({value:p.id,label:p.name}))"/></a-form-item><template v-if="editor==='models'"><a-form-item label="上游模型 ID"><a-input v-model:value="form.model_id"/></a-form-item><a-form-item label="协议适配器"><a-select v-model:value="form.adapter_id" :options="['ark_responses_v1','ark_images_v1'].map(v=>({value:v,label:v}))"/></a-form-item><a-form-item label="完整 HTTPS 接口地址"><a-input v-model:value="form.endpoint"/></a-form-item><a-form-item label="声明能力（必须通过测试）"><a-checkbox-group v-model:value="form.capabilities" :options="['vision','tools','stream','image_generation','reference_image']"/></a-form-item></template><a-form-item label="可用"><a-switch v-model:checked="form.enabled"/></a-form-item><a-alert v-if="editor!=='models'" message="停用供应商或凭证槽位将停止相关配置下发，但不会在供应商处撤销已下发的 Key。" type="warning" class="gap"/><a-form-item v-if="form.id && editor!=='models'" label="启用 / 停用原因"><a-input v-model:value="catalogReason" :maxlength="500"/></a-form-item><a-button type="primary" :loading="busy" @click="saveCatalog">保存</a-button></a-form></a-drawer>
    <a-drawer :open="!!keySlot" title="凭证版本与轮换" :width="560" @close="closeKey"><a-alert message="保存后不再显示完整密钥。先新增版本，测试绑定场景，再激活；旧密钥需在供应商处撤销。" type="info" class="gap"/><a-form layout="vertical"><a-form-item label="新增密钥"><a-input-password v-model:value="secret" autocomplete="new-password"/></a-form-item><a-form-item label="操作原因"><a-input v-model:value="keyReason" :maxlength="500"/></a-form-item><a-button :loading="busy" @click="addKey">保存新版本（不激活）</a-button><a-divider/><a-form-item label="已有版本"><a-select v-model:value="selectedVersion" :options="keyVersions.map(v=>({value:v.version,label:'v'+v.version+' · ****'+v.suffix}))"/></a-form-item><a-form-item label="测试配置"><a-select v-model:value="keyTestRelease" allow-clear placeholder="当前草稿" :options="releases.map(r=>({value:r.id,label:'历史版本 '+r.sequence}))"/></a-form-item><a-space><a-button v-if="can('test')" :loading="busy" @click="testKey">测试绑定（可能计费）</a-button><a-button type="primary" :loading="busy" @click="activate">激活已测试版本</a-button></a-space><p class="gap">若槽位被历史发布引用，请在“测试配置”中逐一选择相关版本，使用新密钥测试通过后再激活。</p></a-form></a-drawer>
    <a-drawer :open="!!preview" title="发布预览" :width="850" @close="preview=null"><a-alert message="新任务使用发布版本；运行中的任务保留原配置。回滚不会恢复已撤销的 Key。" type="info"/><div class="diff"><div><h3>当前版本</h3><pre>{{JSON.stringify(current?.snapshot,null,2)}}</pre></div><div><h3>待发布内容</h3><pre>{{JSON.stringify(preview==='publish'?draft:preview?.snapshot,null,2)}}</pre></div></div><a-textarea v-model:value="reason" placeholder="发布 / 回滚原因（必填）" :maxlength="500" class="gap"/><a-button type="primary" :loading="busy" @click="publish">确认发布</a-button></a-drawer>
    <a-modal v-model:open="controlOpen" title="AI 服务控制" :confirm-loading="busy" @ok="saveControl"><a-alert message="停止下发不等于撤销供应商 Key；紧急泄漏时需同时在供应商控制台禁用。" type="warning" class="gap"/><a-form layout="vertical"><a-form-item label="允许配置下发"><a-switch v-model:checked="controlEnabled"/></a-form-item><a-form-item label="紧急停用场景"><a-checkbox-group v-model:value="disabledScenes" :options="Object.entries(names).map(([value,label])=>({value,label}))"/></a-form-item><a-form-item label="原因"><a-textarea v-model:value="controlReason" :maxlength="500"/></a-form-item></a-form></a-modal>
  </main>
</template>
<style scoped>
.runtime-page{padding:24px;max-width:1600px;margin:auto}header{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}h1{margin:0 0 8px}header p{color:#64748b}.gap{margin:16px 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}.diff{display:grid;grid-template-columns:1fr 1fr;gap:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-width:100%;font-size:12px}.diff>div{min-width:0}.runtime-page :deep(.ant-select){min-width:180px}
</style>
