<template>
 <div class="preset-console">
  <a-page-header title="预设手帐" sub-title="管理系列、手帐、单页和发布版本">
   <template #extra><a-button @click="globalSearchOpen=true">跨页搜索管理</a-button><a-button :loading="loading" @click="run(load)">刷新</a-button><a-button type="primary" @click="openDialog('series')">新增系列</a-button></template>
  </a-page-header>
  <a-alert v-if="error" type="error" show-icon :message="error" closable @close="error=''" />
  <a-alert type="info" show-icon :message="statisticsNotice" style="margin-top:12px" />
  <div class="workspace">
   <a-card title="系列目录" class="series-panel" :loading="loading">
    <a-empty v-if="!series.length" description="暂无系列，请新增系列" />
    <a-menu v-else :selected-keys="seriesID?[String(seriesID)]:[]" @click="({key}:any)=>chooseSeries(Number(key))">
     <a-menu-item v-for="s in series" :key="String(s.id)">{{s.title}} <a-tag v-if="!s.active">已停用</a-tag></a-menu-item>
    </a-menu>
    <a-divider />
    <a-space v-if="selectedSeries"><a-button size="small" @click="openDialog('series',true)">编辑系列</a-button><a-button danger size="small" @click="deleteSeries">删除</a-button></a-space>
   </a-card>
   <div class="content-panel">
    <a-card v-if="selectedSeries" :title="selectedSeries.title+' · 手帐列表'">
     <template #extra><a-space><a-input-search v-model:value="query" placeholder="搜索手帐名称" allow-clear style="width:220px"/><a-button type="primary" @click="openDialog('book')">新增手帐</a-button></a-space></template>
     <a-table :data-source="filteredBooks" :columns="bookColumns" :scroll="{x:1120}" row-key="id" :loading="working" :pagination="{pageSize:8,showSizeChanger:true}">
      <template #bodyCell="{column,record}">
       <template v-if="column.key==='book'"><a-space class="book-name"><a-image v-if="record.cover_url" :src="record.cover_url" :width="45"/><div><a @click="chooseBook(record)">{{record.title}}</a><a-tag v-if="record.content_kind==='album'">相册</a-tag><div class="muted">{{record.description || '暂无简介'}}</div></div></a-space></template>
       <template v-else-if="column.statKey">{{record.import_statistics?.[column.statKey] ?? '暂不可用'}}</template>
       <template v-else-if="column.key==='state'"><a-tag :color="record.active?(record.current?'green':'blue'):'default'">{{!record.active?'已下架':record.current?'已发布':'草稿'}}</a-tag></template>
       <template v-else-if="column.key==='actions'"><a-button type="link" @click="chooseBook(record)">管理单页</a-button></template>
      </template>
     </a-table>
    </a-card>
    <a-empty v-else description="请选择或新增系列" />
    <a-card v-if="book" class="detail-card">
     <a-breadcrumb><a-breadcrumb-item>{{selectedSeries?.title}}</a-breadcrumb-item><a-breadcrumb-item>{{book.title}}</a-breadcrumb-item></a-breadcrumb>
     <div class="book-heading"><div><h2>{{book.title}}</h2><span class="muted">{{pages.length}} 页 · 工作修订 {{book.revision}}</span><a-tag v-if="dirty" color="orange">有未保存调整</a-tag></div>
      <a-space wrap><a-button @click="openDialog('book',true)">编辑手帐</a-button><a-button @click="setActive">{{book.active?'下架':'恢复展示'}}</a-button><a-button :disabled="!dirty" :loading="working" @click="saveDraft">保存草稿</a-button><a-button type="primary" :loading="working" @click="publish">保存并发布</a-button></a-space>
     </div>
     <a-tabs v-model:activeKey="tab">
      <a-tab-pane key="search" tab="跨页与搜索信息"><PresetSearchMetadataPanel :key="book.id" :template-id="book.id" @changed="refreshBookRevision" /></a-tab-pane>
      <a-tab-pane key="pages" tab="页面管理">
       <a-alert type="info" show-icon message="拖动或前后移动可调整页序；修改保存为草稿，发布后客户端生效。" />
       <div class="upload-bar"><a-space wrap>
        <a-select v-model:value="uploadMode" style="width:170px"><a-select-option value="page">添加单页资源包</a-select-option><a-select-option value="book">替换整本资源包</a-select-option></a-select>
        <a-select v-if="uploadMode==='page'" v-model:value="afterPage" style="width:220px"><a-select-option value="">追加到末尾</a-select-option><a-select-option v-for="p in pages" :key="p.id" :value="p.id">插入到 {{p.title}} 之后</a-select-option></a-select>
        <a-button :disabled="!!uploadClient" @click="selectUpload">选择 ZIP 并直传 OSS</a-button>
       </a-space><input ref="inputFile" hidden type="file" accept=".zip" @change="upload($event,uploadMode)" />
       <div class="muted">单页包应包含一页完整图层及素材；整本包将替换当前草稿内容，校验通过后直接发布。</div></div>
       <a-card v-if="uploadStatus" size="small"><a-progress :percent="Math.round(progress*100)" :status="paused?'exception':'active'"/><a-space>{{uploadStatus}}<a-button v-if="uploadClient&&!paused" @click="pauseUpload">暂停</a-button><a-button v-if="paused" @click="resumeUpload">继续</a-button></a-space></a-card>
       <a-empty v-if="!pages.length" description="手帐暂无页面，请上传整本或单页资源包" />
       <div class="pages-grid"><a-card v-for="(p,index) in pages" :key="p.id" size="small" draggable="true" @dragstart="drag=index" @dragover.prevent @drop="move(drag,index)">
        <div class="page-preview" @click="preview=p"><img :src="p.thumbnail" :alt="p.title" loading="lazy"/><a-tag v-if="cover===p.id" color="blue" class="cover-tag">封面</a-tag></div>
        <a-input v-model:value="p.title" :maxlength="200" @change="dirty=true"/><div class="muted">第 {{index+1}} 页 · 添加次数 {{p.import_count ?? '暂不可用'}}</div>
        <a-space wrap><a-button size="small" :disabled="index===0" @click="move(index,index-1)">前移</a-button><a-button size="small" :disabled="index===pages.length-1" @click="move(index,index+1)">后移</a-button><a-button size="small" @click="cover=p.id;dirty=true">设封面</a-button><a-button size="small" danger @click="remove(index)">删除</a-button></a-space>
       </a-card></div>
      </a-tab-pane>
      <a-tab-pane key="statistics" tab="单页添加统计">
       <a-alert type="info" show-icon message="仅统计单页、多选及跨页添加；整本添加不增加单页次数。当前页列表不包含已移除页，可在此查看历史。" />
       <a-space style="margin:12px 0"><a-select v-model:value="statisticsVersion" style="width:180px" @change="run(loadPageStatistics)"><a-select-option value="all">全部版本累计</a-select-option><a-select-option v-for="v in versions" :key="v.number" :value="String(v.number)">版本 {{v.number}}</a-select-option></a-select><a-button @click="run(loadPageStatistics)">刷新统计</a-button></a-space>
       <a-alert v-if="pageStatsError" type="error" message="统计暂不可用，请重试" />
       <a-table v-else :data-source="pageStats" row-key="id" :columns="[{title:'单页',dataIndex:'title'},{title:'来源页 ID',dataIndex:'id'},{title:'添加次数',dataIndex:'count',sorter:(a:any,b:any)=>a.count-b.count},{title:'状态',key:'removed'}]" :scroll="{x:650}"><template #bodyCell="{column,record}"><a-tag v-if="column.key==='removed'">{{record.removed?'已移除':'当前页'}}</a-tag></template></a-table>
      </a-tab-pane>
      <a-tab-pane key="versions" tab="版本记录"><a-table :data-source="versions" row-key="number" :columns="[{title:'版本号',dataIndex:'number'},{title:'发布时间',dataIndex:'created_at'},{title:'操作',key:'action'}]"><template #bodyCell="{column,record}"><a-button v-if="column.key==='action'" type="link" @click="restore(record.number)">回滚并发布</a-button></template></a-table></a-tab-pane>
      <a-tab-pane key="uploads" tab="上传任务"><a-alert type="info" message="ZIP 文件直传 OSS；队列处理需要独立资源处理器在线。" show-icon/><a-button style="margin:12px 0" @click="run(loadHistory)">刷新任务</a-button><a-table :data-source="uploads" row-key="id" :columns="[{title:'创建时间',dataIndex:'created_at'},{title:'模式',dataIndex:'mode'},{title:'状态',dataIndex:'status'},{title:'详情',dataIndex:'error'},{title:'操作',key:'retry'}]"><template #bodyCell="{column,record}"><a-button v-if="column.key==='retry' &amp;&amp; ['failed','conflict'].includes(record.status)" type="link" @click="retryUpload(record.id)">重试</a-button></template></a-table></a-tab-pane>
     <a-tab-pane key="materials" tab="贴纸与背景库"><MaterialLibraryPanel :key="book.id" :template="book.id" /></a-tab-pane>
     </a-tabs>
    </a-card>
   </div>
  </div>
  <a-modal v-model:open="globalSearchOpen" title="全库跨页搜索管理" width="1200px" :footer="null"><PresetSearchMetadataPanel v-if="globalSearchOpen" @changed="refreshBookRevision" /></a-modal>
  <a-modal v-model:open="dialog" :title="(editID?'编辑':'新增')+(dialogKind==='series'?'系列':'手帐')" :confirm-loading="working" @ok="saveDialog" ok-text="保存" cancel-text="取消">
   <a-form layout="vertical"><a-form-item label="名称" required><a-input v-model:value="form.title" :maxlength="120"/></a-form-item>
    <a-form-item v-if="dialogKind==='series'" label="系列标识" required><a-input v-model:value="form.slug" placeholder="如 islands"/></a-form-item>
    <template v-else><a-form-item label="素材类型"><a-select v-model:value="form.content_kind"><a-select-option value="journal">手帐模板</a-select-option><a-select-option value="album">预制相册</a-select-option></a-select></a-form-item><a-form-item label="所属系列"><a-select v-model:value="form.series"><a-select-option v-for="s in series" :key="s.id" :value="s.id">{{s.title}}</a-select-option></a-select></a-form-item><a-form-item label="简介"><a-textarea v-model:value="form.description" :rows="3"/></a-form-item></template>
    <a-form-item label="排序（较小值优先）"><a-input-number v-model:value="form.position" :min="0"/></a-form-item><a-form-item label="启用"><a-switch v-model:checked="form.active"/></a-form-item>
   </a-form>
  </a-modal>
  <a-modal :open="!!preview" :title="preview?.title" :footer="null" width="760px" @cancel="preview=undefined"><img v-if="preview" :src="preview.preview || preview.thumbnail" :alt="preview.title" style="width:100%;max-height:75vh;object-fit:contain"/></a-modal>
 </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { Modal, message } from 'ant-design-vue';
import OSS from 'ali-oss';
import { onBeforeRouteLeave } from 'vue-router';
import http from '../api/http';
import MaterialLibraryPanel from './MaterialLibraryPanel.vue';
import PresetSearchMetadataPanel from './PresetSearchMetadataPanel.vue';
const globalSearchOpen=ref(false);
const statisticsStarted=ref<string>(), statisticsAvailable=ref(false);
const statisticsVersion=ref('all'), pageStats=ref<any[]>([]), pageStatsError=ref(false);
const statisticsNotice=computed(()=>statisticsAvailable.value && statisticsStarted.value
 ? `统计自 ${new Date(statisticsStarted.value).toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai'})} 启用；此前未统计。仅覆盖支持统计的客户端，成功添加后统计，离线操作联网后同步。`
 : '统计启用信息暂不可用；历史添加未统计。');
async function loadPageStatistics(){
 if(!book.value)return;
 const id=book.value.id, version=statisticsVersion.value;
 pageStatsError.value=false;
 try { const data=await get(`templates/${id}/page-statistics/`,{params:version==='all'?{}:{version}});
 if(book.value?.id===id && statisticsVersion.value===version){
 pageStats.value=data.pages;
 if(version==='all'){const counts=new Map<string,number>(data.pages.map((p:any)=>[p.id,p.count]));pages.value=pages.value.map(p=>({...p,import_count:counts.get(p.id)??0}));}
 }
 }catch(e){if(book.value?.id===id){pageStats.value=[];pageStatsError.value=true;}throw e;}
}
async function refreshBookRevision(){if(book.value){const data=await get(`templates/${book.value.id}/`);book.value={...book.value,revision:data.revision};}}
const base = '/api/admin/v1/diary-presets/';
async function get(path: string, config?: any): Promise<any> { return http.get(base + path, config); }
async function post(path: string, body?: any): Promise<any> { return http.post(base + path, body); }
async function patch(path: string, body?: any): Promise<any> { return http.patch(base + path, body); }
async function put(path: string, body?: any): Promise<any> { return http.put(base + path, body); }

interface Series { id: number; title: string; slug: string; position: number; active: boolean }
interface Book { content_kind?: string; id: string; title: string; revision: number; active: boolean; cover_url?: string; page_count: number; series: number; position: number; description: string; current?: number; import_statistics?: Record<string, number> | null }
interface Page { id: string; title: string; thumbnail: string; preview?: string; import_count?: number }
const series = ref<Series[]>([]), books = ref<Book[]>([]), pages = ref<Page[]>([]);
const seriesID = ref<number>(), book = ref<Book>(), cover = ref(''), drag = ref(0), error = ref('');
const loading = ref(false), working = ref(false), dirty = ref(false), query = ref(''), tab = ref('pages');
const progress = ref(0), uploadStatus = ref(''), paused = ref(false);
let uploadClient: OSS | undefined, checkpoint: any, source: File | undefined, sessionID = '', key = '', poll: ReturnType<typeof setTimeout> | undefined;
async function run(fn: () => Promise<void>) { error.value = ''; working.value = true; try { await fn(); } catch (e) { error.value = e instanceof Error ? e.message : String(e); message.error(error.value); } finally { working.value = false; } }
const selectedSeries = computed(() => series.value.find(s => s.id === seriesID.value));
const filteredBooks = computed(() => books.value.filter(b => b.title.toLowerCase().includes(query.value.toLowerCase())));
const versions = ref<Array<{ number: number; created_at: string }>>([]);
const uploads = ref<any[]>([]);
const preview = ref<Page>();
const dialog = ref(false), dialogKind = ref('series'), editID = ref<number | string>();
const form = ref({ content_kind: 'journal', title: '', slug: '', description: '', position: 0, active: true, series: 0 });
const uploadMode = ref('page'), afterPage = ref('');
const inputFile = ref<HTMLInputElement>();
const bookColumns = [
 {title:'手帐',key:'book',width:260}, {title:'页数',dataIndex:'page_count',width:80},
 ...[['整本添加','book_count'],['选页添加','selection_count'],['选页累计页数','selected_page_count'],['使用人数','user_count']].map(([title,key])=>({title,key,statKey:key,width:125,sorter:(a:Book,b:Book)=>(a.import_statistics?.[key!] ?? -1)-(b.import_statistics?.[key!] ?? -1)})),
 {title:'状态',key:'state',width:100}, {title:'排序',dataIndex:'position',width:80}, {title:'操作',key:'actions',width:180}
];
function ask(title: string, content: string): Promise<boolean> {
 return new Promise(resolve => Modal.confirm({ title, content, okText:'确认', cancelText:'取消', onOk:()=>{resolve(true);}, onCancel:()=>{resolve(false);} }));
}
async function canLeave() { if(uploadClient && !paused.value){message.warning('请先完成或暂停当前上传');return false;} return !dirty.value || await ask('有未保存的页面调整', '切换后会丢失尚未保存的排序、标题和删除操作，是否继续？'); }
async function load() {
 loading.value=true;
 try {
  series.value=await get('series/');
  try {const meta=await get('templates/statistics-metadata/');statisticsStarted.value=meta.started_at;statisticsAvailable.value=true;}catch{statisticsAvailable.value=false;}
  if(seriesID.value){books.value=await get('templates/',{params:{series:seriesID.value}});if(book.value)await loadPageStatistics();}
  if (series.value.length && !seriesID.value) await chooseSeries(series.value[0]!.id);
 } finally {loading.value=false;}
}
async function chooseSeries(id: number) {
 if (!await canLeave()) return;
 await run(async()=>{seriesID.value=id;book.value=undefined;dirty.value=false;pages.value=[];
 books.value=await get('templates/',{params:{series:id}});});
}
async function chooseBook(b: Book) {
 if (!await canLeave()) return;
 await run(async()=>{
 const data=await get(`templates/${b.id}/pages/`);
 book.value={...b,revision:data.revision};pages.value=data.pages;cover.value=data.cover;
 dirty.value=false;tab.value='pages';statisticsVersion.value='all';await loadHistory();await loadPageStatistics();
 });
}
async function loadHistory() {
 if(!book.value)return;
 versions.value=await get(`templates/${book.value.id}/versions/`);
 uploads.value=await get('uploads/',{params:{template:book.value.id}});
}
function openDialog(kind: string, edit=false) {
 dialogKind.value=kind;editID.value=edit ? (kind==='series'?selectedSeries.value?.id:book.value?.id):undefined;
 const value=kind==='series'?selectedSeries.value:book.value;
 form.value={content_kind:edit&&kind==='book'?book.value?.content_kind||'journal':'journal',title:edit?value?.title||'':'',slug:edit&&kind==='series'?selectedSeries.value?.slug||'':'',
 description:edit&&kind==='book'?book.value?.description||'':'',position:edit?value?.position||0:0,
 active:edit?value?.active??true:true,series:seriesID.value||0};dialog.value=true;
}
async function saveDialog() {
 if(!form.value.title.trim() || (dialogKind.value==='series'&&!form.value.slug.trim())){message.warning('请填写名称和系列标识');return;}
 await run(async()=>{
 if(dialogKind.value==='series'){
 const payload={title:form.value.title,slug:form.value.slug,position:form.value.position,active:form.value.active};
 if(editID.value) await patch(`series/${editID.value}/`,payload); else await post('series/',payload);
 series.value=await get('series/');
 }else{
 const payload={...form.value,revision:book.value?.revision};
 const value=editID.value?await patch(`templates/${editID.value}/`,payload):await post('templates/',payload);
 if(form.value.series===seriesID.value){books.value=await get('templates/',{params:{series:seriesID.value}});dirty.value=false;await chooseBook(value);}
 else {book.value=undefined;dirty.value=false;books.value=await get('templates/',{params:{series:seriesID.value}});}
 }
 dialog.value=false;message.success('已保存');
 });
}
async function deleteSeries() {
 if(!await ask('删除空系列','有手帐的系列无法删除，可先移动手帐或停用系列。'))return;
 await run(async()=>{await http.delete(base+`series/${seriesID.value}/`);seriesID.value=undefined;book.value=undefined;dirty.value=false;await load();});
}
function move(from:number,to:number){if(from<0||to<0||to>=pages.value.length)return;const item=pages.value.splice(from,1)[0]!;pages.value.splice(to,0,item);dirty.value=true;}
async function remove(index:number){if(pages.value.length<=1){message.warning('手帐至少保留一页');return;}if(!await ask('删除单页','从下一版本移除此页，已发布历史版本保留。'))return;const p=pages.value.splice(index,1)[0];if(p?.id===cover.value)cover.value=pages.value[0]?.id??'';dirty.value=true;}
async function savePages(){
 if(!book.value)return;
 book.value=await put(`templates/${book.value.id}/pages/`,{revision:book.value.revision,page_ids:pages.value.map(p=>p.id),cover_page_id:cover.value,titles:Object.fromEntries(pages.value.map(p=>[p.id,p.title]))});dirty.value=false;
}
async function saveDraft(){await run(async()=>{await savePages();message.success('草稿已保存，客户端仍使用已发布版本');});}
async function publish(){if(!await ask('发布手帐','自动校验通过后立即对客户端生效，无需人工审核。'))return;await run(async()=>{if(dirty.value)await savePages();book.value=await post(`templates/${book.value!.id}/publish/`,{revision:book.value!.revision});books.value=await get('templates/',{params:{series:seriesID.value}});await chooseBook(book.value!);message.success('已发布新版本');});}
async function setActive(){if(!book.value)return;await run(async()=>{book.value=await patch(`templates/${book.value!.id}/`,{revision:book.value!.revision,active:!book.value!.active});books.value=await get('templates/',{params:{series:seriesID.value}});message.success('状态已更新');});}
async function restore(version:number){if(!await ask('回滚到版本 '+version,'将创建一个新的发布版本，当前未保存调整会被替换。'))return;await run(async()=>{book.value=await post(`templates/${book.value!.id}/rollback/`,{revision:book.value!.revision,version});dirty.value=false;await chooseBook(book.value!);message.success('已回滚并发布');});}
async function retryUpload(id:string){await run(async()=>{await post(`uploads/${id}/retry/`,{revision:book.value!.revision,after_page:afterPage.value});await loadHistory();message.success('已重新加入处理队列');});}
function selectUpload(){if(dirty.value){message.warning('请先保存页面调整，再上传资源');return;}inputFile.value?.click();}
const checkpointKey = 'diary-preset-upload-checkpoint';
function saveCheckpoint() {
  if (!source) return;
  const safe = checkpoint ? { ...checkpoint, file: undefined } : undefined;
  localStorage.setItem(checkpointKey, JSON.stringify({ sessionID, key, checkpoint: safe,
    name: source.name, size: source.size, modified: source.lastModified, template: book.value?.id }));
}
async function upload(event: Event, mode: string) { const input=event.target as HTMLInputElement; source=input.files?.[0]; if (!source) return;
const saved = JSON.parse(localStorage.getItem(checkpointKey) || 'null');
if (saved && saved.template === book.value?.id && saved.name === source.name && saved.size === source.size && saved.modified === source.lastModified && await ask('恢复未完成上传','已找到同一文件的上传记录，是否继续？')) {
  sessionID=saved.sessionID; key=saved.key; checkpoint=saved.checkpoint; await resumeUpload(); return;
}
checkpoint=undefined; progress.value=0; await run(async()=>{ const data=(await post('uploads/', {template:book.value!.id,revision:book.value!.revision,mode,after_page:mode==='page'?afterPage.value:'',size:source!.size})); sessionID=data.id; key=data.credentials.key; uploadClient=new OSS({...data.credentials,refreshSTSToken:async()=>{ const c=(await post(`uploads/${sessionID}/refresh/`)); return c; },refreshSTSTokenInterval:300000}); await send(); }); }
async function send() { if (!source || !uploadClient) return; paused.value=false; uploadStatus.value='正在直传 OSS'; try { await uploadClient.multipartUpload(key,source,{checkpoint,headers:{'x-oss-object-acl':'private'},partSize:8*1024*1024,parallel:3,progress:async(p,c)=>{progress.value=p;checkpoint=c;saveCheckpoint();}}); await post(`uploads/${sessionID}/complete/`); localStorage.removeItem(checkpointKey); uploadClient=undefined; uploadStatus.value='上传完成，云端正在校验'; await status(); } catch(e) { if (!paused.value) { uploadClient=undefined; throw e; } } }
function pauseUpload(){ paused.value=true; uploadClient?.cancel(); uploadStatus.value='已暂停'; }
async function resumeUpload(){ await run(async()=>{ const c=(await post(`uploads/${sessionID}/refresh/`)); uploadClient=new OSS(c); await send(); }); }
async function status(){ await run(async()=>{const data=(await get(`uploads/${sessionID}/`)); uploadStatus.value=data.error || ({queued:'等待云端处理',processing:'云端校验中',published:'发布成功'} as Record<string,string>)[data.status] || data.status; await loadHistory(); if(['queued','processing'].includes(data.status)) poll=setTimeout(status,3000); else if(data.status==='published' && book.value) await chooseBook(book.value); }); }
onBeforeRouteLeave(async()=>await canLeave());
onMounted(()=>run(load));
onUnmounted(()=>{if(poll)clearTimeout(poll);uploadClient?.cancel();});
</script>
<style scoped>
.preset-console{min-height:80vh}.book-name{min-width:210px}.book-name a{overflow-wrap:break-word}.workspace{display:flex;gap:20px;margin-top:16px;align-items:flex-start}.series-panel{width:230px;flex-shrink:0}.content-panel{flex:1;min-width:0}.detail-card{margin-top:20px}.book-heading{display:flex;justify-content:space-between;gap:16px;align-items:center;margin:20px 0}.book-heading h2{margin:0 0 8px}.muted{color:#8c8c8c;font-size:12px;margin-top:5px}.pages-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:16px;margin-top:20px}.page-preview{position:relative;height:245px;cursor:zoom-in;background:#fafafa;margin-bottom:12px}.page-preview img{width:100%;height:100%;object-fit:contain}.cover-tag{position:absolute;top:8px;left:8px}.upload-bar{margin:16px 0}.pages-grid .ant-space{margin-top:10px}@media(max-width:900px){.workspace{display:block}.series-panel{width:100%;margin-bottom:16px}.book-heading{display:block}}
</style>
