<template>
  <a-alert v-if="error" :message="error" type="error" show-icon />
  <p>关联整本手帐后，其所有页面均可使用配套素材。配置在下一次发布整本手帐时生效，历史版本保持原关联。</p>
  <a-button :loading="loading" @click="load">刷新关联</a-button>
  <a-list :data-source="rows" :loading="loading"><template #renderItem="{item}"><a-list-item>
    <span>{{item.template_title}} · {{item.type==='sticker'?'贴纸':'背景'}} → {{item.library_title || '未关联'}} <template v-if="item.library_id">v{{item.library_version || '待发布'}}</template></span>
    <a-button v-if="canEdit && item.library_id" danger :disabled="busy" @click="unlink(item)">取消关联</a-button>
  </a-list-item></template></a-list>
  <a-empty v-if="!loading && !rows.length" description="暂无下一版本的配套关联" />
  <a-form v-if="canEdit" layout="vertical">
    <a-form-item v-if="!template" label="选择整本手帐"><a-select v-model:value="chosenTemplate" style="width:100%" show-search allow-clear :filter-option="false" :options="choices" :loading="searching" @search="searchChoices" @change="loadBookConfig" /></a-form-item>
    <a-form-item v-else label="素材类型"><a-select v-model:value="chosenType" :options="[{value:'sticker',label:'贴纸'},{value:'background',label:'背景'}]" @change="changeType" /></a-form-item>
    <a-form-item v-if="!library" label="选择已发布素材包"><a-select v-model:value="chosenLibrary" style="width:100%" show-search allow-clear :filter-option="false" :options="choices" :loading="searching" @search="searchChoices" @change="loadVersions" /></a-form-item>
    <p v-if="current?.library_id">当前配套：{{current.library_title}} v{{current.library_version}}。保存将替换下一版本的配套配置。</p>
    <a-form-item label="固定素材包版本"><a-select v-model:value="chosenVersion" :options="versions.map(v=>({value:v,label:'v'+v}))" style="width:180px" /></a-form-item>
    <a-button type="primary" :loading="busy" :disabled="loading || configLoading || !configReady || !chosenTemplate || !chosenLibrary || !chosenVersion" @click="save">{{current?.library_id?'保存配套关联':'关联整本手帐'}}</a-button>
  </a-form>
</template>
<script setup lang="ts">
import {ref, computed, watch, onBeforeUnmount} from 'vue';
import {Modal} from 'ant-design-vue';
import http from '../api/http';
const props=defineProps<{template?:string; library?:any; canEdit:boolean}>();
const emit=defineEmits<{changed:[]}>();
const base='/api/v1/materials/manage/';
const rows=ref<any[]>([]), choices=ref<any[]>([]), versions=ref<number[]>([]), bookRows=ref<any[]>([]);
const chosenTemplate=ref<string>(), chosenLibrary=ref<string>(), chosenType=ref('sticker'), chosenVersion=ref<number>();
const error=ref(''),loading=ref(false),searching=ref(false),busy=ref(false),configLoading=ref(false),configReady=ref(false);
let session=0, searchRequest=0, configRequest=0, versionRequest=0;
const current=computed(()=>bookRows.value.find(r=>r.type===chosenType.value));
function fail(e:any){error.value=e.message || '请求失败，请重试'}
async function searchChoices(q=''){
 const token=++searchRequest;searching.value=true;
 try{const result:any=await http.get(base+(props.library?'templates/':'libraries/'),{params:{q,type:chosenType.value,include_linked:1,state:props.library?undefined:'published',paged:1,page_size:100}});
  if(token===searchRequest)choices.value=(result.items || result).map((r:any)=>({value:r.id,label:r.title+(r.version?' · v'+r.version:' · 未发布')}));
 }catch(e){if(token===searchRequest)fail(e)}finally{if(token===searchRequest)searching.value=false}
}
async function loadBookConfig(){
 const token=++configRequest;bookRows.value=[];configReady.value=false;
 if(!chosenTemplate.value)return;configLoading.value=true;
 try{const result:any=await http.get(base+`templates/${chosenTemplate.value}/links/`);if(token===configRequest){bookRows.value=result.items;configReady.value=true}}
 catch(e){if(token===configRequest)fail(e)}finally{if(token===configRequest)configLoading.value=false}
}
async function loadVersions(){
 const token=++versionRequest;versions.value=[];chosenVersion.value=undefined;if(!chosenLibrary.value)return;
 try{const result:any=await http.get(base+`libraries/${chosenLibrary.value}/links/`);if(token===versionRequest){versions.value=result.versions;chosenVersion.value=versions.value[0]}}
 catch(e){if(token===versionRequest)fail(e)}
}
async function load(){
 const token=++session;error.value='';loading.value=true;
 try{const result:any=await http.get(base+(props.library?`libraries/${props.library.id}/links/`:`templates/${props.template}/links/`));
  if(token!==session)return;rows.value=result.items;
  if(props.library){versions.value=result.versions;chosenVersion.value=props.library.version || result.versions[0]}else{bookRows.value=result.items;configReady.value=true}
 }catch(e){if(token===session)fail(e)}finally{if(token===session)loading.value=false}
}
function changeType(){chosenLibrary.value=undefined;chosenVersion.value=undefined;versions.value=[];void searchChoices('')}
async function commit(body:any,templateID:string){
 busy.value=true;error.value='';const token=session;
 try{await http.post(base+`templates/${templateID}/links/`,body);if(token!==session)return;await load();if(props.library)await loadBookConfig();emit('changed')}
 catch(e){if(token===session)fail(e);throw e}finally{busy.value=false}
}
function save(){
 if(!chosenTemplate.value||!chosenLibrary.value||!chosenVersion.value)return;
 const id=chosenTemplate.value,body={type:chosenType.value,library_id:chosenLibrary.value,library_version:chosenVersion.value,linked:true,expected_revision:current.value?.revision || 0};
 Modal.confirm({title:'确认保存整本手帐配套关联？',content:'将在下一次发布整本手帐时生效；现有手帐版本与作品保持不变。',onOk:()=>commit(body,id)});
}
function unlink(row:any){Modal.confirm({title:'确认取消整本手帐关联？',content:'下一次发布将不再附带此素材包，历史版本和用户作品保留。',onOk:()=>commit({type:row.type,linked:false,expected_revision:row.revision},row.template_id)})}
watch(()=>[props.template,props.library?.id],()=>{
 session++;configRequest++;versionRequest++;searchRequest++;rows.value=[];bookRows.value=[];versions.value=[];choices.value=[];
 chosenTemplate.value=props.template;chosenLibrary.value=props.library?.id;chosenType.value=props.library?.type || 'sticker';chosenVersion.value=undefined;configReady.value=false;
 void load();void searchChoices('');
},{immediate:true});
onBeforeUnmount(()=>{session++;configRequest++;versionRequest++;searchRequest++});
</script>
