<template>
 <a-card title="批量同步到生产">
  <a-alert type="info" show-icon message="选择资源后预览固定版本与自动依赖。确认后逐项进行生产预检、提交和验收；复用共享 OSS 文件。" />
  <a-alert v-if="error" type="error" :message="error" show-icon style="margin-top:12px" />
  <a-alert v-if="!enabled" type="warning" :message="reason || '当前环境未启用发送'" style="margin-top:12px" />
  <a-space style="margin:16px 0" wrap>
   <a-select v-model:value="filter" style="width:150px"><a-select-option value="all">全部资源</a-select-option><a-select-option v-for="(name,key) in names" :key="key" :value="key">{{name}}</a-select-option></a-select>
   <a-select v-model:value="statusFilter" style="width:150px"><a-select-option value="pending">待同步</a-select-option><a-select-option value="synced">已同步</a-select-option><a-select-option value="all">全部状态</a-select-option></a-select>
   <a-input-search v-model:value="query" placeholder="搜索资源名称" allow-clear />
   <a-button @click="refresh">刷新</a-button><a-button @click="selectAll">选择所有可同步资源</a-button><a-button @click="selected=[]">清空选择</a-button>
   <a-button type="primary" :disabled="!enabled || !selected.length" :loading="busy" @click="preview">预览同步清单（{{selected.length}}）</a-button>
  </a-space>
  <a-table row-key="key" :data-source="filtered" :columns="columns" :row-selection="{selectedRowKeys:selected,onChange:(keys:any)=>selected=keys,getCheckboxProps:(r:any)=>({disabled:!r.selectable})}" :pagination="{pageSize:20}">
   <template #bodyCell="{column,record}"><template v-if="column.key==='type'">{{names[record.type]}}</template><template v-if="column.key==='sync'"><a-tag :color="record.sync_state==='succeeded'?'green':record.sync_state==='running'?'blue':'default'">{{record.sync_label || '未同步'}}</a-tag></template><template v-if="column.key==='availability'">{{record.reason || (record.owner_id?'随所属整本同步':'可同步')}}</template></template>
  </a-table>
  <h3>最近批次</h3>
  <a-list :data-source="history"><template #renderItem="{item}"><a-list-item><a-button type="link" @click="open(item)">{{item.created_at}} · {{labels[item.state] || item.state}} · {{item.entries.length}} 项</a-button></a-list-item></template></a-list>
 </a-card>
 <a-modal v-model:open="visible" title="同步清单与进度" width="1000px" :footer="null">
  <a-alert v-if="error" type="error" :message="error" show-icon />
  <template v-if="batch">
   <a-alert type="info" :message="'批次：'+batch.id+' · '+(labels[batch.state] || batch.state)" />
   <p>包含自动依赖。已有生产价格保留；首次收费内容遵循销售开关及策略依赖检查。批次内各整本分别原子提交。</p>
   <a-table row-key="key" :data-source="batch.entries" :pagination="false" :columns="planColumns" :scroll="{y:450}">
    <template #bodyCell="{column,record}"><template v-if="column.key==='type'">{{names[record.type]}}</template><template v-if="column.key==='state'">{{labels[record.state] || record.state}}<div>{{record.message || record.task?.result?.message}}</div></template><template v-if="column.key==='dependencies'">{{record.reason}}<div v-if="record.via">{{record.via}}</div></template></template>
   </a-table>
   <a-space style="margin-top:16px"><a-button v-if="batch.state==='preview'" type="primary" :loading="busy" @click="confirm">确认以上版本并同步到生产</a-button><a-button v-if="batch.state==='partial'" :loading="busy" @click="retry">仅重试失败项</a-button><a-button @click="poll">刷新结果</a-button></a-space>
  </template>
 </a-modal>
</template>
<script setup lang="ts">
import {ref,computed,onMounted,onBeforeUnmount} from 'vue';
import http from '../api/http';
const base='/api/admin/v1/content-sync/';
const rows=ref<any[]>([]),selected=ref<string[]>([]),history=ref<any[]>([]),batch=ref<any>(),filter=ref('all'),statusFilter=ref('pending'),query=ref('');
const enabled=ref(false),reason=ref(''),error=ref(''),busy=ref(false),visible=ref(false);
let timer:ReturnType<typeof setTimeout>|undefined;
const names:Record<string,string>={template:'模板',sticker:'贴纸',background:'背景',font:'字体'};
const labels:Record<string,string>={preview:'待确认清单',pending:'待处理',running:'处理中',embedded:'随整本提交',succeeded:'已完成',partial:'部分失败',failed:'失败',blocked:'依赖未完成'};
const columns=[{title:'资源',dataIndex:'title'},{title:'类型',key:'type'},{title:'发布版本',dataIndex:'version'},{title:'同步状态',key:'sync'},{title:'说明',key:'availability'}];
const planColumns=[{title:'资源',dataIndex:'title'},{title:'类型',key:'type'},{title:'固定版本',dataIndex:'version'},{title:'依赖',key:'dependencies'},{title:'状态',key:'state'}];
const filtered=computed(()=>rows.value.filter(r=>(filter.value==='all'||r.type===filter.value)&&r.title.includes(query.value)&&(statusFilter.value==='all'||(statusFilter.value==='synced'?r.sync_state==='succeeded':r.sync_state!=='succeeded'))));
function selectAll(){selected.value=filtered.value.filter(r=>r.selectable).map(r=>r.key);}
async function run(fn:()=>Promise<void>){busy.value=true;error.value='';try{await fn();}catch(e:any){error.value=e?.response?.data?.message||e?.message||'请求失败';}finally{busy.value=false;}}
async function refresh(){await run(async()=>{const data:any=await http.get(base+'catalog/');rows.value=data.items;enabled.value=data.enabled;reason.value=data.reason;selected.value=selected.value.filter(key=>rows.value.some(r=>r.key===key&&r.selectable));history.value=await http.get(base+'batches/');});}
async function preview(){await run(async()=>{batch.value=await http.post(base+'batches/',{selection:rows.value.filter(r=>selected.value.includes(r.key)).map(r=>({kind:r.kind,id:r.id}))});visible.value=true;});}
function open(value:any){batch.value=value;visible.value=true;poll();}
async function confirm(){await run(async()=>{batch.value=await http.post(base+'batches/'+batch.value.id+'/confirm/',{plan_hash:batch.value.plan_hash});await poll();});}
async function retry(){await run(async()=>{batch.value=await http.post(base+'batches/'+batch.value.id+'/retry/',{});await poll();});}
async function poll(){clearTimeout(timer);if(!batch.value)return;const id=batch.value.id;try{const data:any=await http.get(base+'batches/'+id+'/');if(batch.value?.id===id){const previous=batch.value.state;batch.value=data;if(previous!==data.state&&['succeeded','partial'].includes(data.state))await refresh();}}catch(e:any){error.value=e?.message||'查询失败';}if(visible.value&&batch.value?.state==='running')timer=setTimeout(poll,2000);}
onMounted(refresh);onBeforeUnmount(()=>clearTimeout(timer));
</script>
