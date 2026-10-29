<template>
  <a-alert v-if="error" :message="error" type="error" show-icon />
  <a-tabs @change="loadHistory">
    <a-tab-pane key="recycle" tab="回收站">
      <p>整套删除后停止新获取，保留历史记录及文件。恢复后保持下架，需要手动上架。</p>
      <a-button :loading="loading" @click="loadRecycle">刷新回收站</a-button>
      <a-table :data-source="recycled" :columns="[{title:'素材包',dataIndex:'title'},{title:'删除时间',dataIndex:'deleted_at'},{title:'原因',dataIndex:'deletion_reason'},{title:'操作',key:'actions'}]" row-key="id" :pagination="{current:page,pageSize:20,total,showSizeChanger:false}" @change="(p:any)=>loadRecycle(p.current)">
        <template #bodyCell="{column,record}"><a-button v-if="column.key==='actions' && canDelete" :disabled="busy" @click="restore(record)">恢复为下架状态</a-button></template>
      </a-table>
    </a-tab-pane>
    <a-tab-pane key="cleanup" tab="OSS 清理">
      <a-alert message="当前可清理过期上传临时文件。正式图片因历史版本、共享包及跨环境引用保护而保留，不会随删除整套被物理删除。" type="info" show-icon />
      <a-space style="margin:16px 0"><a-button v-if="canDelete" :loading="busy" @click="scan">扫描过期临时文件</a-button><a-button @click="loadJobs">刷新任务</a-button></a-space>
      <a-list :data-source="jobs"><template #renderItem="{item}"><a-list-item>
        <div>{{item.created_at}} · {{stateLabel(item.state)}} · 已清理 {{item.completed}} / {{item.total}} 个会话 · 失败 {{item.failed}}
          <p>{{item.note}}</p><a-collapse v-if="item.entries.length"><a-collapse-panel key="details" header="查看文件及处理结果"><p v-for="entry in item.entries" :key="entry.upload_id">{{entry.name}} · {{stateLabel(entry.state)}} {{entry.error}}</p></a-collapse-panel></a-collapse>
        </div>
        <a-button v-if="canDelete && item.state!=='completed' && item.total" :disabled="busy" @click="confirmClean(item)">{{item.state==='preview'?'清理临时文件':'继续 / 重试'}}</a-button>
      </a-list-item></template></a-list>
    </a-tab-pane>
  </a-tabs>
  <a-drawer :open="!!linkLibrary" title="关联整本手帐" width="650" @close="linkLibrary=null">
    <MaterialBookLinks v-if="linkLibrary" :key="linkLibrary.id" :library="linkLibrary" :can-edit="canLink" @changed="emit('changed')" />
  </a-drawer>
  <a-modal :open="!!deletion" title="删除整套 · 影响预览" :confirm-loading="busy" ok-text="移入回收站" :ok-button-props="{danger:true,disabled:!deletion || !!deletion.links.length || confirmTitle!==deletion.title}" @cancel="deletion=null" @ok="remove">
    <template v-if="deletion">
      <a-alert v-if="error" :message="error" type="error" />
      <p>{{deletion.title}} · {{deletion.materials}} 张素材 · {{deletion.versions}} 个版本</p>
      <p>下一版本关联 {{deletion.links.length}} 本手帐；历史固定引用 {{deletion.historical_bindings.length}} 条。</p>
      <p>保留 {{deletion.resources}} 个正式资源，约 {{(deletion.protected_bytes/1024/1024).toFixed(2)}} MB。</p>
      <a-alert :message="deletion.cleanup_reason" type="info" />
      <a-alert v-if="deletion.links.length" message="请先在“关联整本手帐”中取消全部关联，再重新检查删除影响。" type="warning" />
      <a-input v-model:value="confirmTitle" placeholder="输入完整素材包名称以确认" style="margin-top:16px" />
      <a-textarea v-model:value="reason" :maxlength="300" placeholder="删除原因（可选）" style="margin-top:12px" />
    </template>
  </a-modal>
</template>
<script setup lang="ts">
import {ref,onBeforeUnmount} from 'vue';
import {Modal} from 'ant-design-vue';
import http from '../api/http';
import MaterialBookLinks from './MaterialBookLinks.vue';
const props=defineProps<{canDelete:boolean;canLink:boolean;type?:string}>();
const emit=defineEmits<{changed:[]}>();
const base='/api/v1/materials/manage/';
const error=ref(''),loading=ref(false),busy=ref(false),recycled=ref<any[]>([]),jobs=ref<any[]>([]),page=ref(1),total=ref(0);
const deletion=ref<any>(null),linkLibrary=ref<any>(null),confirmTitle=ref(''),reason=ref('');
let disposed=false,previewRequest=0,recycleRequest=0;
const stateLabel=(s:string)=>({preview:'待确认',pending:'待继续',partial:'部分完成',completed:'已完成',failed:'失败',deleted:'已清理',blocked:'受保护'}[s]||s);
function fail(e:any){error.value=e.message||'请求失败，请重试'}
async function loadRecycle(target=page.value){const token=++recycleRequest;loading.value=true;error.value='';try{const result:any=await http.get(base+'libraries/',{params:{recycle:1,paged:1,page:target,page_size:20,type:props.type||undefined}});if(token===recycleRequest){recycled.value=result.items;total.value=result.total;page.value=result.page}}catch(e){fail(e)}finally{if(token===recycleRequest)loading.value=false}}
async function loadJobs(){try{jobs.value=await http.get(base+'cleanup/');error.value=''}catch(e){fail(e)}}
function loadHistory(key:string|number){if(key==='cleanup')void loadJobs();else void loadRecycle()}
async function scan(){busy.value=true;error.value='';try{await http.post(base+'cleanup/',{});await loadJobs()}catch(e){fail(e)}finally{busy.value=false}}
function confirmClean(job:any){Modal.confirm({title:`确认清理 ${job.total-job.completed} 个过期上传会话的临时文件？`,content:'只删除临时上传目录，正式图片保留。失败后可以继续重试。',onOk:()=>clean(job)})}
async function clean(job:any){busy.value=true;error.value='';try{let result:any;do{result=await http.post(base+`cleanup/${job.id}/execute/`,{});const i=jobs.value.findIndex(j=>j.id===job.id);if(i>=0)jobs.value[i]=result}while(!disposed && result.state==='pending')}catch(e){fail(e);throw e}finally{busy.value=false}}
function restore(row:any){Modal.confirm({title:'确认恢复素材包？',content:'恢复后保持下架，原手帐配套关系不会自动重建。',onOk:async()=>{busy.value=true;try{await http.post(base+`libraries/${row.id}/recycle/`,{operation:'restore',expected_state_revision:row.state_revision});await loadRecycle();emit('changed')}catch(e){fail(e);throw e}finally{busy.value=false}}})}
async function previewDelete(library:any){const token=++previewRequest;error.value='';try{const result:any=await http.get(base+`libraries/${library.id}/deletion-preview/`);if(token!==previewRequest)return;deletion.value=result;confirmTitle.value='';reason.value=''}catch(e){fail(e)}}
async function remove(){if(!deletion.value||busy.value)return;busy.value=true;error.value='';try{const d=deletion.value;await http.post(base+`libraries/${d.id}/recycle/`,{operation:'delete',token:d.token,expected_state_revision:d.state_revision,confirm_title:confirmTitle.value,reason:reason.value});deletion.value=null;await loadRecycle();emit('changed')}catch(e){fail(e)}finally{busy.value=false}}
defineExpose({refresh:loadRecycle,openLinks:(library:any)=>{linkLibrary.value=library},previewDelete});
onBeforeUnmount(()=>{disposed=true;previewRequest++;recycleRequest++});
</script>
