<template>
  <a-modal v-model:open="visible" title="同步到生产" :footer="null" width="720px">
    <a-alert v-if="error" :message="error" type="error" show-icon/>
    <template v-if="record">
      <h3>{{record.title}} · 本地 v{{record.version}}</h3>
      <p>目标：生产环境。复用共享 OSS 文件，确认后发布该版本。</p>
      <a-alert v-if="record.has_draft_changes" message="本地存在未发布修改，本次仅同步已发布版本。" type="warning"/>
      <a-space><a-button :loading="busy" :disabled="busy || active" @click="preflight">重新预检</a-button><a-button @click="history">同步历史</a-button></a-space>
      <div v-if="task" class="sync-result">
        <p>状态：{{stateLabel(task.state)}} · 任务 {{task.id}}</p>
        <p v-if="task.result?.total">OSS 已检查 {{task.result.checked || 0}} / {{task.result.total}}</p>
        <template v-if="task.result?.target_version!==undefined">
          <p>生产当前 v{{task.result.target_version}} · {{task.result.count}} 项素材</p>
          <p>新增 {{task.result.added || 0}} · 更新 {{task.result.updated || 0}} · 移出本包 {{task.result.removed || 0}}</p>
        </template>
        <a-alert v-if="task.result?.message" :message="task.result.message" :type="task.state==='succeeded'?'success':'info'"/>
        <p v-if="task.commit_status==='committed'">内容已写入生产，重试仅核对结果。</p>
        <p v-if="task.state==='ready'">预检有效至 {{task.expires_at}}。{{task.result?.no_op?'内容已一致，确认后记录同步结果，不新增版本。':'确认后生产将发布 v'+task.result.next_version+'。'}}</p>
        <a-button v-if="task.state==='ready'" type="primary" :loading="busy" @click="confirm">{{task.result?.no_op?'确认内容一致':'确认同步并发布'}}</a-button>
        <a-button v-if="['outcome_unknown','committed_verification_pending'].includes(task.state)" :loading="busy" @click="retry">重新确认生产结果</a-button>
      </div>
      <a-list v-if="historyRows.length" :data-source="historyRows" :pagination="{current:historyPage,pageSize:20,total:historyTotal,onChange:history}"><template #renderItem="{item}"><a-list-item><a-button type="link" @click="task=item;poll()">{{item.created_at}} · 来源 v{{item.source_version}} · {{stateLabel(item.state)}}</a-button></a-list-item></template></a-list>
    </template>
  </a-modal>
</template>
<script setup lang="ts">
import {ref,computed,onMounted,onBeforeUnmount} from 'vue';
import http from '../api/http';
const emit=defineEmits(['options','synced']);
const base='/api/v1/materials/manage/';
const visible=ref(false),busy=ref(false),record=ref<any>(null),task=ref<any>(null),error=ref('');
const historyRows=ref<any[]>([]),historyPage=ref(1),historyTotal=ref(0);
let timer:ReturnType<typeof setTimeout>|undefined;let generation=0;
const active=computed(()=>task.value&&['preflighting','queued','checking','importing','committed','verifying','outcome_unknown','committed_verification_pending'].includes(task.value.state));
const labels:Record<string,string>={preflighting:'正在预检',ready:'等待确认',queued:'排队中',checking:'正在核对生产',importing:'导入中',committed:'已提交',verifying:'正在验收',succeeded:'已同步',no_op:'内容一致',conflict:'存在冲突',expired:'预检已过期',failed:'失败',outcome_unknown:'正在确认生产结果',committed_verification_pending:'已提交，验收待确认'};
const stateLabel=(s:string)=>labels[s]||s;
function message(e:any){return e?.response?.data?.message||e?.response?.data?.detail||e?.message||'同步请求失败，请刷新结果后重试';}
async function poll(){
  clearTimeout(timer);if(!task.value||!visible.value)return;
  const id=task.value.id,gen=generation;
  try{const data:any=await http.get(base+'sync-tasks/'+id+'/');if(gen!==generation)return;task.value=data;if(data.state==='succeeded')emit('synced');}
  catch(e){if(gen===generation)error.value=message(e);}
  if(gen===generation&&visible.value&&active.value&&!document.hidden)timer=setTimeout(poll,5000);
}
async function history(page=1){try{const data:any=await http.get(base+'libraries/'+record.value.id+'/sync-history/',{params:{page}});historyRows.value=data.items;historyTotal.value=data.total;historyPage.value=page;}catch(e){error.value=message(e);}}
async function open(r:any){generation++;clearTimeout(timer);record.value=r;task.value=null;historyRows.value=[];error.value='';visible.value=true;await history();if(historyRows.value.length){task.value=historyRows.value[0];poll();}else await preflight();}
async function preflight(){busy.value=true;error.value='';try{const data:any=await http.post(base+'libraries/'+record.value.id+'/production-sync/preflight/',{source_version:record.value.version,expected_state_revision:record.value.state_revision});task.value=data;poll();}catch(e){error.value=message(e);}finally{busy.value=false;}}
async function confirm(){busy.value=true;error.value='';try{const data:any=await http.post(base+'sync-tasks/'+task.value.id+'/confirm/',{preflight_token:task.value.result.target_fingerprint});task.value=data;poll();}catch(e){error.value=message(e);}finally{busy.value=false;}}
async function retry(){busy.value=true;try{await http.post(base+'sync-tasks/'+task.value.id+'/retry/',{});poll();}catch(e){error.value=message(e);}finally{busy.value=false;}}
function visibility(){if(!document.hidden&&visible.value)poll();}
onMounted(async()=>{document.addEventListener('visibilitychange',visibility);try{const data:any=await http.get(base+'sync/options/');emit('options',data);}catch{emit('options',{can_sync:false,enabled:false});}});
onBeforeUnmount(()=>{generation++;clearTimeout(timer);document.removeEventListener('visibilitychange',visibility);});
defineExpose({open});
</script>
