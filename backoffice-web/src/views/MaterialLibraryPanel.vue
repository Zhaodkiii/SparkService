<template>
 <a-alert v-if="error" :message="error" type="error" closable @close="error=''"/>
 <a-space><a-button @click="load">刷新素材库</a-button><span>在转换工具发布素材后，可在此管理分类、关键词和顺序。</span></a-space>
 <a-tabs>
  <a-tab-pane v-for="lib in libraries" :key="lib.id" :tab="lib.type==='background'?'背景库':'贴纸库'">
   <h3>{{lib.title}} · {{lib.favorite_count}} 人收藏 · v{{lib.version}}</h3>
   <a-button @click="openAvailable(lib)">从全局素材库添加</a-button>
   <a-input-search v-model:value="search" placeholder="搜索名称、分类、关键词" allow-clear/>
   <a-table :data-source="lib.items.filter((i:any)=>matches(i))" :columns="columns" row-key="id" :pagination="{pageSize:20}">
    <template #bodyCell="{column,record}">
     <a-image v-if="column.key==='image'" :src="record.thumbnail_url" :width="70"/>
     <a-input v-else-if="column.key==='name'" v-model:value="record.name" :maxlength="120"/>
     <a-select v-else-if="column.key==='category'" :value="record.kind+'/'+record.subcategory" style="width:180px" @change="(v:string)=>setCategory(record,v)">
      <template v-for="c in categories.filter((c:any)=>(c.kind==='background')===(lib.type==='background'))" :key="c.kind">
       <a-select-option v-for="s in c.subcategories" :key="c.kind+'/'+s.id" :value="c.kind+'/'+s.id">{{c.title}} / {{s.title}}</a-select-option>
      </template>
     </a-select>
     <div v-else-if="column.key==='keywords'"><a-select v-model:value="record.keywords" mode="tags" style="min-width:180px" placeholder="关键词"/><a-select v-model:value="record.aliases" mode="tags" style="min-width:180px" placeholder="别名"/></div>
     <span v-else-if="column.key==='favorites'">{{record.favorite_count}}</span>
     <a-space v-else-if="column.key==='actions'"><a-button @click="move(lib,record,-1)">上移</a-button><a-button @click="move(lib,record,1)">下移</a-button><a-button danger @click="lib.items=lib.items.filter((i:any)=>i.id!==record.id)">移除</a-button></a-space>
    </template>
   </a-table>
   <a-button type="primary" :loading="saving" @click="save(lib)">校验并发布当前素材库</a-button>
  </a-tab-pane>
 </a-tabs>
 <a-modal v-model:open="adding" title="选择已有素材（共享资源）" :footer="null"><a-input-search v-model:value="availableQuery" @search="()=>loadAvailable()" placeholder="名称或关键词"/><a-list :data-source="available"><template #renderItem="{item}"><a-list-item><a-space><a-image :src="item.thumbnail_url" :width="45"/>{{item.name}}<a-button :disabled="target?.items.some((i:any)=>i.id===item.id)" @click="target.items.push({...item})">加入当前库</a-button></a-space></a-list-item></template></a-list><a-button v-if="availableNext" @click="loadAvailable(true)">更多</a-button></a-modal>
 <a-empty v-if="!loading && !error && !libraries.length" description="当前手帐尚未发布素材库"/>
</template>
<script setup lang="ts">
import {ref,watch} from 'vue';
import http from '../api/http';
const props=defineProps<{template:string}>();
const libraries=ref<any[]>([]),categories=ref<any[]>([]),search=ref(''),error=ref(''),saving=ref(false),loading=ref(false);
const base='/api/v1/materials/';
const adding=ref(false),target=ref<any>(null),available=ref<any[]>([]),availableQuery=ref(''),availableNext=ref<number|null>(null);
async function openAvailable(lib:any){target.value=lib;adding.value=true;await loadAvailable()}
async function loadAvailable(more=false){try{const data=await http.get<unknown, {items:any[];next:number|null}>(base+'available/',{params:{type:target.value.type,q:availableQuery.value,after:more?availableNext.value:0}});available.value=more?available.value.concat(data.items):data.items;availableNext.value=data.next}catch(e:any){error.value=e.message}}
const columns=[{title:'预览',key:'image'},{title:'名称',key:'name'},{title:'分类',key:'category'},{title:'关键词 / 别名',key:'keywords'},{title:'收藏人数',key:'favorites'},{title:'操作',key:'actions'}];
function matches(i:any){return [i.name,i.kind,i.subcategory,...i.keywords,...i.aliases].join(' ').includes(search.value)}
function setCategory(i:any,v:string){[i.kind,i.subcategory]=v.split('/')}
function move(lib:any,item:any,delta:number){const i=lib.items.indexOf(item),j=i+delta;if(j>=0&&j<lib.items.length){lib.items.splice(i,1);lib.items.splice(j,0,item)}}
async function load(){
 const template=props.template;
 loading.value=true;error.value='';libraries.value=[];
 try{
  const [a,b]=await Promise.all([http.get<unknown,any[]>(base+'manage/'+template+'/'),http.get<unknown,any[]>(base+'categories/')]);
  if(template!==props.template)return;
  if(!Array.isArray(a)||!Array.isArray(b))throw new Error('素材库响应格式异常，请刷新重试');
  libraries.value=a;categories.value=b;
 }catch(e:any){if(template===props.template)error.value=e.message}
 finally{if(template===props.template)loading.value=false}
}
async function save(lib:any){saving.value=true;try{await http.post(base+'manage/'+props.template+'/',{library:lib.id,version:lib.version,items:lib.items});await load()}catch(e:any){error.value=JSON.stringify(e.response?.data||e.message)}finally{saving.value=false}}
watch(()=>props.template,load,{immediate:true});
</script>
