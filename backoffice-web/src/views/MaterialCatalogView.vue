<template>
  <section class="materials">
    <div class="page-heading"><div><h1>素材管理</h1><p>维护素材包、更新素材版本，并确认客户端展示范围。</p></div></div>
    <a-alert v-if="uploadEnabled===false" :message="uploadUnavailableReason || 'OSS 上传暂不可用，请检查 OSS 配置'" type="warning" show-icon />
    <a-alert v-if="notice" :message="notice" type="success" closable @close="notice=''" />
    <a-alert v-if="error" :message="error" type="error" closable @close="error=''" />
    <p v-if="syncOptions.can_sync">环境：{{syncOptions.environment}} · 目标：生产环境 <small v-if="!syncOptions.enabled">{{syncOptions.reason}}</small></p>
    <MaterialProductionSync ref="productionSync" @options="value=>syncOptions=value" @synced="load()"/>
    <a-tabs v-model:activeKey="tab">
      <a-tab-pane key="packs" tab="贴纸包与背景库">
        <a-space wrap><a-input-search v-model:value="query" placeholder="搜索名称" @search="load(1)"/><a-button @click="load()">刷新</a-button><a-button type="primary" v-if="permissions.can_edit" @click="openCreate">新建素材包</a-button><a-select v-if="!fixedType" v-model:value="filterType" style="width:120px" :options="[{value:'',label:'全部类型'},{value:'sticker',label:'贴纸'},{value:'background',label:'背景'}]"/><a-select v-model:value="filterOrigin" style="width:130px" :options="[{value:'',label:'全部来源'},{value:'independent',label:'独立主题'},{value:'template',label:'模板关联'}]"/><a-select v-model:value="filterState" style="width:130px" :options="[{value:'',label:'全部状态'},{value:'published',label:'已上架'},{value:'draft',label:'未发布'},{value:'withdrawn',label:'已下架'}]"/></a-space>
        <a-table :data-source="filteredLibraries" :columns="columns" row-key="id" :loading="loading" :scroll="{x:1100}" :pagination="{current:libraryPage,pageSize:20,total:libraryTotal,showSizeChanger:false,showTotal:(total:number)=>`共 ${total} 个素材包`}" @change="(p:any)=>load(p.current)">
          <template #bodyCell="{column,record}">
            <div v-if="column.key==='summary'" class="pack-summary"><a-image v-if="record.cover" :src="record.cover.url" :width="64"/><span v-else class="missing-cover">待补封面</span><div><strong>{{record.title}}</strong><small>{{record.type==='sticker'?'贴纸包':'背景库'}} · {{record.template_title || '独立主题'}}</small></div></div>
            <span v-else-if="column.key==='count'">{{record.count}} / {{record.total_count ?? record.count}}</span>
            <span v-else-if="column.key==='display'">{{record.gallery_visible?'贴纸馆可见':'贴纸馆未展示'}}<small v-if="record.display_reason">{{record.display_reason}}</small><small v-if="record.template_id">配套管理：更多 → 关联整本手帐</small></span>
            <span v-else-if="column.key==='production_sync'">{{record.production_sync?.label || '—'}}<small v-if="record.production_sync?.target_version">生产 v{{record.production_sync.target_version}}</small><small v-if="record.production_sync?.checked_at">核实：{{dayjs(record.production_sync.checked_at).format('MM-DD HH:mm')}}</small></span>
            <span v-else-if="column.key==='updated'">{{record.updated_at?dayjs(record.updated_at).format('MM-DD HH:mm'):'—'}}<small>{{record.updated_by || ''}}</small></span>

            <span v-else-if="column.key==='sort'">{{record.featured?'推荐 · ':''}}{{record.sort_order}}</span>
            <span v-else-if="column.key==='state'">{{record.version===0?'未发布':record.active?'已发布':'已下架'}} · v{{record.version}}<small v-if="record.has_draft_changes" class="draft-badge">有未发布修改</small></span>
            <a-space v-else-if="column.key==='actions'">
              <a-button @click="edit(record)">{{permissions.can_edit?'编辑':'查看'}}</a-button>
              <a-dropdown :trigger="['click']"><a-button>更多</a-button><template #overlay><a-menu :selectable="false">
                <a-menu-item v-if="syncOptions.can_sync" :disabled="!syncOptions.enabled || !record.version || !record.active || !!record.template_id || record.type!=='sticker'" @click="productionSync?.open(record)">同步到生产</a-menu-item>
                <a-menu-item @click="lifecycle?.openLinks(record)">关联整本手帐</a-menu-item>
                <a-menu-item v-if="permissions.can_delete" danger @click="lifecycle?.previewDelete(record)">删除整套</a-menu-item>
                <a-menu-item @click="history(record)">历史版本</a-menu-item>
                <a-menu-item v-if="permissions.can_edit" @click="error='';placementEdit={...record}">展示设置</a-menu-item>
                <a-menu-item v-if="permissions.can_takedown" :disabled="!record.version" :danger="record.active" @click="confirmLibraryAvailability(record)">{{record.active?'下架素材包':'上架素材包'}}</a-menu-item>
              </a-menu></template></a-dropdown>
            </a-space>
          </template>
        </a-table>
      </a-tab-pane>
      <a-tab-pane key="items" tab="单张素材">
        <a-input-search v-model:value="materialQuery" placeholder="搜索素材" @search="loadMaterials(1)"/>
        <a-list :data-source="materials" :loading="materialsLoading" :pagination="{current:materialPage,pageSize:20,total:materialTotal,showSizeChanger:false,onChange:(page:number)=>loadMaterials(page)}"><template #renderItem="{item}"><a-list-item><a-space><a-image :src="item.thumbnail_url" :width="64"/><span>{{item.name}} · {{item.kind}} / {{item.subcategory}}</span><a-button v-if="permissions.can_edit" @click="editMaterial(item)">修改信息</a-button><a-button @click="showUsage(item)">查看引用</a-button><a-button v-if="permissions.can_takedown" danger @click="confirmMaterialAvailability(item)">{{item.active?'全局下架':'恢复上架'}}</a-button></a-space></a-list-item></template></a-list>
      </a-tab-pane>
      <a-tab-pane key="dictionary" tab="分类与标签">
        <a-space wrap><a-select v-model:value="dictionaryTarget" :options="[{value:'categories',label:'分类'},{value:'tags',label:'标签'}]" @change="loadDictionary"/><a-button @click="loadDictionary">刷新</a-button><a-button v-if="permissions.can_edit" @click="dictionaryEdit={title:'',active:true,kind:'illustration',subcategory:''}">新增</a-button></a-space>
        <a-list :data-source="dictionaryRows"><template #renderItem="{item}"><a-list-item>{{item.title}} · {{item.kind}} {{item.subcategory}} · {{item.active?'启用':'停用'}}<a-button v-if="permissions.can_edit" @click="dictionaryEdit={...item}">编辑</a-button></a-list-item></template></a-list>
      </a-tab-pane>
      <a-tab-pane key="audit" tab="发布与操作记录"><a-button @click="loadAudit">刷新</a-button><a-table :data-source="logs" :columns="[{title:'操作',dataIndex:'action'},{title:'时间',dataIndex:'created_at'},{title:'操作者',dataIndex:'actor_id'},{title:'详情',key:'detail'}]" row-key="id"><template #bodyCell="{column,record}"><code v-if="column.key==='detail'">{{JSON.stringify(record.detail)}}</code></template></a-table></a-tab-pane>
      <a-tab-pane key="lifecycle" tab="回收站与 OSS 清理" force-render><MaterialLifecyclePanel ref="lifecycle" :type="fixedType" :can-delete="permissions.can_delete" :can-link="permissions.can_link" @changed="load()" /></a-tab-pane>
    </a-tabs>
    <a-modal :open="!!placementEdit" title="展示设置" @cancel="placementEdit=null" @ok="savePlacement"><a-alert v-if="placementEdit && error" :message="error" type="error"/><a-form v-if="placementEdit" layout="vertical"><a-form-item label="推荐"><a-switch v-model:checked="placementEdit.featured"/></a-form-item><a-form-item label="推荐顺序（数字越小越靠前，推荐包优先）"><a-input-number v-model:value="placementEdit.sort_order" :min="0"/></a-form-item><a-form-item label="上新标记截止时间（本地时区）"><a-date-picker :value="placementEdit.new_until?dayjs(placementEdit.new_until):null" show-time @change="(v:any)=>placementEdit.new_until=v?v.toISOString():null"/></a-form-item></a-form></a-modal>
    <a-modal :open="!!dictionaryEdit" title="维护分类或标签" @cancel="dictionaryEdit=null" @ok="saveDictionary"><template v-if="dictionaryEdit"><a-alert v-if="error" :message="error" type="error"/><a-input v-model:value="dictionaryEdit.title" placeholder="中文名称"/><template v-if="dictionaryTarget==='categories'"><a-select v-model:value="dictionaryEdit.kind" :options="categories.map(c=>({value:c.kind,label:c.title}))"/><a-input v-model:value="dictionaryEdit.subcategory" placeholder="英文稳定标识，如 botanical" :disabled="!!dictionaryEdit.id"/></template><a-switch v-model:checked="dictionaryEdit.active" checked-children="启用" un-checked-children="停用"/></template></a-modal>
    <a-modal v-model:open="creating" title="新建素材包" :confirm-loading="creatingBusy" @ok="create">
      <a-alert v-if="error" :message="error" type="error"/>
      <a-form layout="vertical"><a-form-item label="素材包名称" required><a-input v-model:value="newTitle" placeholder="例如：秋日旅行" :maxlength="60"/></a-form-item>
      <a-form-item label="类型"><a-select v-if="!fixedType" v-model:value="newType" :options="[{value:'sticker',label:'贴纸'},{value:'background',label:'背景'}]" @change="newTemplate='';searchTemplates('')"/></a-form-item>
      <a-form-item label="关联整本手帐（可选，下一次发布手帐时生效）"><a-select v-model:value="newTemplate" allow-clear show-search :filter-option="false" :loading="templatesLoading" :options="templateOptions" placeholder="按模板名称搜索" @search="searchTemplates"/></a-form-item></a-form>
    </a-modal>
    <a-drawer :open="!!selected" width="min(1100px, 96vw)" title="素材包草稿" @close="closeEditor">
      <template v-if="draft && selected">
        <a-alert v-if="error" :message="error" type="error" show-icon/>
        <a-alert v-if="notice" :message="notice" type="success" show-icon/>
        <a-alert v-if="uploadEnabled===false" :message="uploadUnavailableReason || 'OSS 上传暂不可用，当前可选用已有素材'" type="warning"/>
        <p>当前发布版本：v{{baseVersion}}。保存草稿不会改变客户端内容；发布新版本后，已下架的包仍保持下架。</p>
        <a-collapse v-if="bindings.length"><a-collapse-panel key="bindings" header="模板固定版本关联"><p v-for="binding in bindings" :key="binding.preset_version__template_id+':'+binding.preset_version__number">{{binding.preset_version__template__title || selected.template_title || '关联模板'}} v{{binding.preset_version__number}} → 素材包 v{{binding.library_version__number}}</p><p>发布素材包不会替换历史模板绑定，请在发布新模板版本时确认配套内容。</p></a-collapse-panel></a-collapse>
        <a-alert v-if="dirty" message="有未保存修改，请保存后发布或离开。" type="warning"/>
        <a-form layout="vertical" :disabled="!permissions.can_edit || saving">
          <a-form-item label="名称"><a-input v-model:value="draft.title" :maxlength="60" @change="dirty=true"/></a-form-item>
          <a-form-item label="介绍"><a-textarea v-model:value="draft.description" :maxlength="1000" @change="dirty=true"/></a-form-item>
          <a-form-item label="标签"><a-select v-model:value="draft.tags" mode="tags" @change="dirty=true"/></a-form-item>
          <p class="upload-help">封面：至少 512×512 方图；展示图：宽度至少 750px，最多 8 张；贴纸：透明 PNG/WebP，单张最多 10MB。浏览器本地检查并生成缩略图，两张图片均直传 OSS。</p><a-space wrap><label>封面 <input type="file" :disabled="uploadEnabled!==true || !permissions.can_edit || saving" accept="image/png,image/webp,image/jpeg" @change="e=>uploadFiles(e,'cover')"/></label><label>展示图 <input type="file" :disabled="uploadEnabled!==true || !permissions.can_edit || saving" multiple accept="image/png,image/webp,image/jpeg" @change="e=>uploadFiles(e,'preview')"/></label><label>单张素材 <input type="file" :disabled="uploadEnabled!==true || !permissions.can_edit || saving" multiple :accept="selected.type==='background'?'image/png,image/webp,image/jpeg':'image/png,image/webp'" @change="e=>uploadFiles(e,selected.type)"/></label></a-space>
          <a-space wrap><a-image v-if="images[draft.cover]" :src="images[draft.cover].url" :width="100"/><div v-for="(id,index) in draft.previews" :key="id"><a-image v-if="images[id]" :src="images[id].url" :width="100"/><a-button size="small" @click="draft.previews.splice(index,1);dirty=true">移除展示图</a-button></div></a-space>
          <a-list :data-source="uploads"><template #renderItem="{item}"><a-list-item>{{item.name}} · {{uploadStateLabel(item.state)}} {{item.progress || 0}}% {{item.error}}<a-button v-if="item.state==='failed'" :disabled="item.running" @click="runUpload(item)">重试</a-button><a-button v-if="item.state==='failed'" @click="discardUpload(item)">放弃此文件</a-button></a-list-item></template></a-list>
          <a-button :disabled="!permissions.can_edit || saving" @click="showPicker">从全局素材加入</a-button><a-button :disabled="!outdatedCount || !permissions.can_edit || saving" @click="updateAllItems">更新 {{outdatedCount}} 张素材至最新版本</a-button>
          <a-space wrap><a-button @click="selectAllItems">全选 / 取消全选</a-button><a-select v-model:value="batchCategory" :options="categoryOptions" placeholder="批量分类" style="width:220px"/><a-button :disabled="!selectedItems.length || !batchCategory" @click="applyBatchCategory">应用至所选</a-button></a-space>
          <a-list :data-source="draft.items" bordered><template #renderItem="{item,index}"><a-list-item :draggable="permissions.can_edit && !saving" @dragstart="dragIndex=index" @dragover.prevent @drop="drop(index)"><a-space><a-checkbox :checked="selectedItems.includes(item.revision)" @change="toggleItem(item.revision)"/><a-image v-if="itemIndex[item.revision]" :src="itemIndex[item.revision].thumbnail_url" :width="60"/><span>{{itemIndex[item.revision]?.name || item.revision}}</span><a-button v-if="latestFor(item)?.revision > item.revision" @click="updateItem(item)">更新版本</a-button><a-button @click="move(index,-1)">上移</a-button><a-button @click="move(index,1)">下移</a-button><a-button danger @click="draft.items.splice(index,1);dirty=true">从本包移除</a-button></a-space></a-list-item></template></a-list>
        </a-form>
        <div class="editor-footer"><small>{{saving?'正在保存或校验…':dirty?'草稿有未保存修改':draftSavedAt?'草稿已保存 · '+dayjs(draftSavedAt).format('HH:mm:ss'):'当前草稿已加载'}}</small><p v-if="publishIssues.length">发布前需处理：{{publishIssues.join('；')}}</p><a-space><a-button v-if="permissions.can_edit" :loading="saving" @click="save">保存草稿</a-button><a-button @click="reloadDraft">重新加载草稿</a-button><a-button @click="preview=true">手机预览</a-button><a-button v-if="permissions.can_publish" type="primary" :disabled="dirty || publishIssues.length>0" :loading="saving" @click="reviewPublish">校验并发布</a-button></a-space></div>
      </template>
    </a-drawer>
    <a-modal v-model:open="picking" title="选择已有素材" :footer="null"><a-input-search v-model:value="materialQuery" @search="loadMaterials(1)"/><a-list :data-source="materials.filter(m=>m.active)" :loading="materialsLoading" :pagination="{current:materialPage,pageSize:20,total:materialTotal,showSizeChanger:false,onChange:(page:number)=>loadMaterials(page)}"><template #renderItem="{item}"><a-list-item><a-space><a-image :src="item.thumbnail_url" :width="50"/>{{item.name}}<a-button :disabled="draft?.items.some((i:any)=>itemIndex[i.revision]?.id===item.id)" @click="addItem(item)">加入</a-button></a-space></a-list-item></template></a-list></a-modal>
    <a-modal v-model:open="usageOpen" title="素材引用范围" :footer="null"><a-alert v-if="error" :message="error" type="error"/><p>{{usageNote}}</p><a-list :data-source="usageRows"><template #renderItem="{item}"><a-list-item>{{item.title}} v{{item.version}} · 素材版本 {{item.revision}}<small>{{item.current?'当前发布包':'历史模板固定引用'}} · {{item.active?'包已启用':'包已下架'}}<template v-if="item.template"> · {{item.template}} 模板 v{{item.template_versions.join('、')}}</template></small></a-list-item></template></a-list><a-empty v-if="!usageRows.length" description="暂无当前发布包或固定模板引用"/></a-modal>
    <a-modal v-model:open="preview" title="手机预览" :footer="null"><div class="phone" v-if="draft"><h2>{{draft.title}}</h2><p>{{draft.description}}</p><img v-for="id in draft.previews" :key="id" :src="images[id]?.url"/><div class="grid"><img v-for="item in draft.items" :key="item.revision" :src="itemIndex[item.revision]?.thumbnail_url"/></div></div></a-modal>
    <a-modal v-model:open="showHistory" title="历史版本" :footer="null"><a-list :data-source="versions"><template #renderItem="{item}"><a-list-item>v{{item.version}} · {{item.created_at}}<a-button v-if="permissions.can_edit" @click="restore(item.version)">恢复为新草稿</a-button></a-list-item></template></a-list></a-modal>
    <a-modal :open="!!editingMaterial" title="素材信息（创建新版本）" @cancel="editingMaterial=null" @ok="saveMaterial"><template v-if="editingMaterial"><a-alert v-if="error" :message="error" type="error"/><p>保存将创建新素材版本。引用本素材的包需在草稿中更新版本并重新发布。</p><a-input v-model:value="editingMaterial.name" :maxlength="60"/><label>替换图片（直传 OSS，发布新包版本后生效）<input type="file" :disabled="uploadEnabled!==true || !permissions.can_edit || saving" :accept="editingMaterial.kind==='background'?'image/png,image/webp,image/jpeg':'image/png,image/webp'" @change="replaceMaterialFile"/></label><span v-if="replacementUpload">{{replacementUpload.state}} · {{replacementUpload.progress}}% {{replacementUpload.error}}</span><a-select v-model:value="editingCategory" style="width:100%" :options="categoryOptions"/><a-select v-model:value="editingMaterial.keywords" mode="tags" style="width:100%" placeholder="关键词"/><a-select v-model:value="editingMaterial.aliases" mode="tags" style="width:100%" placeholder="别名"/></template></a-modal>
  </section>
</template>
<script setup lang="ts">
import {ref,reactive,onMounted,onBeforeUnmount,watch,computed} from 'vue';
import {Modal} from 'ant-design-vue';
import {useRoute} from 'vue-router';
const route=useRoute();
const fixedType=typeof route?.meta?.fixedMaterialType==='string'?route.meta.fixedMaterialType:'';
import MaterialProductionSync from './MaterialProductionSync.vue';
import MaterialLifecyclePanel from './MaterialLifecyclePanel.vue';
const lifecycle=ref<InstanceType<typeof MaterialLifecyclePanel>>();
const productionSync=ref<InstanceType<typeof MaterialProductionSync>>();
const syncOptions=ref<any>({can_sync:false,enabled:false});
import {prepareMaterialImage,putImageToOSS} from './materialImageUpload';
import dayjs from 'dayjs';
import http from '../api/http';
import {readUploads,rememberUpload,forgetUpload,createUploadLimiter} from './materialUploadTasks';
const base='/api/v1/materials/';
const libraries=ref<any[]>([]),materials=ref<any[]>([]),logs=ref<any[]>([]),versions=ref<any[]>([]),categories=ref<any[]>([]);
const filterType=ref(fixedType),filterOrigin=ref(''),filterState=ref('');
const filteredLibraries=computed(()=>libraries.value.filter(l=>(!filterType.value||l.type===filterType.value)&&(!filterOrigin.value||l.origin_type===filterOrigin.value)&&(!filterState.value||(l.publication_state || (l.version===0?'draft':l.active?'published':'withdrawn'))===filterState.value)));
const libraryPage=ref(1),libraryTotal=ref(0),materialPage=ref(1),materialTotal=ref(0),materialsLoading=ref(false);let materialRequest=0;
const permissions=reactive({can_edit:true,can_publish:true,can_takedown:true,can_delete:false,can_link:false});const accountID=ref<string>('');
const creatingBusy=ref(false),templatesLoading=ref(false),templateOptions=ref<any[]>([]),usageOpen=ref(false),usageRows=ref<any[]>([]),usageNote=ref('');let templateRequest=0;
const loading=ref(false),saving=ref(false),error=ref(''),query=ref(''),materialQuery=ref(''),tab=ref('packs');
const selected=ref<any>(null),draft=ref<any>(null),revision=ref(0),baseVersion=ref(0),dirty=ref(false),images=ref<Record<string,any>>({}),itemIndex=ref<Record<number,any>>({});
const creating=ref(false),newTitle=ref(''),newType=ref(fixedType||'sticker'),newTemplate=ref(''),picking=ref(false),preview=ref(false),showHistory=ref(false),historyLibrary=ref<any>(null),dragIndex=ref(-1),editingMaterial=ref<any>(null),editingCategory=ref('');
const replacementUpload=ref<any>(null);
const uploads=ref<any[]>([]);const uploadLimit=createUploadLimiter(3);
const uploadStateLabel=(state:string)=>({queued:'等待处理',processing:'本地处理',uploading:'直传 OSS 中',confirming:'确认文件中',verified:'已确认',failed:'待处理'}[state] || state);
function discardUpload(task:any){forgetUpload(accountID.value,task.uploadID);uploads.value=uploads.value.filter(t=>t!==task)}
function uploadInContent(task:any,content:any){return task.attachedRevision?content.items.some((i:any)=>i.revision===task.attachedRevision):task.attachedResource&&(content.cover===task.attachedResource||content.previews.includes(task.attachedResource))}
let disposed=false;let publishKey='';let editSession=0;let listRequest=0;let autoSaveTimer:ReturnType<typeof setTimeout>|undefined;const selectedItems=ref<number[]>([]),batchCategory=ref('');
const dictionaryTarget=ref('categories'),dictionaryRows=ref<any[]>([]),dictionaryEdit=ref<any>(null);
const columns=[{title:'素材包',key:'summary',width:290},{title:'有效 / 总数',key:'count',width:100},{title:'发布状态',key:'state',width:140},{title:'客户端展示',key:'display',width:170},{title:'推荐顺序',key:'sort',width:110},{title:'生产同步',key:'production_sync',width:150},{title:'更新信息',key:'updated',width:130},{title:'操作',key:'actions',width:180}];
const placementEdit=ref<any>(null);
async function savePlacement(){const lib=placementEdit.value;try{await http.patch(base+`manage/libraries/${lib.id}/placement/`,{expected_state_revision:lib.state_revision,featured:lib.featured,sort_order:lib.sort_order,new_until:lib.new_until||null});placementEdit.value=null;await load();notice.value='展示设置已保存'}catch(e){fail(e)}}
const draftSavedAt=ref<number>();
const uploadUnavailableReason=ref('');
const notice=ref(''),uploadEnabled=ref<boolean|undefined>(),latestItems=ref<any[]>([]),bindings=ref<any[]>([]);
const latestFor=(item:any)=>latestItems.value.find(m=>m.id===itemIndex.value[item.revision]?.id);
const outdatedCount=computed(()=>draft.value?.items.filter((i:any)=>latestFor(i)?.revision>i.revision).length||0);
function updateItem(item:any){const oldRevision=item.revision;const latest=latestFor(item);if(!latest||latest.revision<=item.revision)return;itemIndex.value[latest.revision]=latest;item.revision=latest.revision;selectedItems.value=selectedItems.value.map(id=>id===oldRevision?latest.revision:id);dirty.value=true}
function updateAllItems(){draft.value.items.forEach(updateItem)}
const publishIssues=computed(()=>{if(!draft.value)return [];const issues=[];if(!draft.value.cover)issues.push('添加封面');if(!draft.value.previews?.length)issues.push('添加展示图');if(!draft.value.items?.length)issues.push('添加素材');if(uploads.value.some(u=>u.state==='failed'))issues.push('重试或放弃失败文件');if(uploads.value.some(u=>!['verified','failed'].includes(u.state)))issues.push('等待图片处理与上传确认完成');return issues});

const categoryOptions=computed(()=>categories.value.filter(c=>!selected.value || ((c.kind==='background')===(selected.value.type==='background'))).flatMap(c=>c.subcategories.map((s:any)=>({value:c.kind+'/'+s.id,label:c.title+' / '+s.title}))));
function fail(e:any){error.value=typeof e.message==='string'?e.message:'请求失败，请重试'}
async function load(page=libraryPage.value){const token=++listRequest;loading.value=true;try{const result:any=await http.get(base+'manage/libraries/',{params:{q:query.value,paged:1,page,page_size:20,type:filterType.value||undefined,origin:filterOrigin.value||undefined,state:filterState.value||undefined}});if(token===listRequest){libraries.value=Array.isArray(result)?result:result.items;libraryPage.value=Array.isArray(result)?page:result.page;libraryTotal.value=Array.isArray(result)?result.length:result.total;error.value=''}}catch(e){if(token===listRequest)fail(e)}finally{if(token===listRequest)loading.value=false}}
async function openCreate(){error.value='';creating.value=true;await searchTemplates('')}
async function searchTemplates(q:string){const token=++templateRequest;templatesLoading.value=true;try{const result:any=await http.get(base+'manage/templates/',{params:{q,type:newType.value,paged:1,page_size:100}});if(token===templateRequest)templateOptions.value=(Array.isArray(result)?result:result.items).map((t:any)=>({value:t.id,label:`${t.title} · ${t.series || ''} · ${t.version?'v'+t.version:'尚未发布'}`}))}catch(e){if(token===templateRequest)fail(e)}finally{if(token===templateRequest)templatesLoading.value=false}}
async function create(){if(!newTitle.value.trim()){error.value='请输入素材包名称';return}if(creatingBusy.value)return;creatingBusy.value=true;try{const created:any=await http.post(base+'manage/libraries/',{title:newTitle.value,type:newType.value,template_id:newTemplate.value||null});creating.value=false;newTitle.value='';newTemplate.value='';await load(1);await edit(created)}catch(e){fail(e)}finally{creatingBusy.value=false}}

async function edit(lib:any){try{if(!lib)return;const token=++editSession;selectedItems.value=[];const d:any=await http.get(base+`manage/libraries/${lib.id}/draft/`);if(token!==editSession)return;error.value='';draftSavedAt.value=undefined;selected.value=lib;latestItems.value=d.latest_items||[];bindings.value=d.bindings||[];if(typeof d.uploads_enabled==='boolean')uploadEnabled.value=d.uploads_enabled;if(d.upload_unavailable_reason)uploadUnavailableReason.value=d.upload_unavailable_reason;draft.value=d.content;revision.value=d.revision;baseVersion.value=d.base_version;images.value=d.images;itemIndex.value=Object.fromEntries(d.items.map((i:any)=>[i.revision,i]));dirty.value=false;uploads.value=readUploads(accountID.value).filter(t=>t.libraryID===lib.id).filter(t=>{if(uploadInContent(t,d.content)){forgetUpload(accountID.value,t.uploadID);return false}return true}).map(t=>({...t,state:'failed',progress:100,error:'文件已直传 OSS，点击重试确认并加入此草稿',editSession:token}));publishKey=''}catch(e){fail(e)}}
function finishEditor(){clearTimeout(autoSaveTimer);editSession++;selected.value=null;void load()}
function closeEditor(){if(dirty.value||uploads.value.some(u=>!['verified','failed'].includes(u.state))){Modal.confirm({title:'草稿尚未保存或上传处理中，确认离开？',onOk:finishEditor})}else{finishEditor()}}
async function save(){if(!selected.value||saving.value)return;const libID=selected.value.id,session=editSession;error.value='';const content=JSON.parse(JSON.stringify(draft.value));const previous=JSON.stringify(content);saving.value=true;try{const d:any=await http.patch(base+`manage/libraries/${libID}/draft/`,{expected_draft_revision:revision.value,content});if(session!==editSession)return;revision.value=d.revision;draftSavedAt.value=Date.now();dirty.value=JSON.stringify(draft.value)!==previous;for(const task of uploads.value){if(task.state==='verified'&&uploadInContent(task,content))forgetUpload(accountID.value,task.uploadID)}publishKey=''}catch(e){fail(e)}finally{saving.value=false}}
async function reviewPublish(){if(publishIssues.value.length||dirty.value||saving.value)return;const session=editSession,libID=selected.value.id,draftRevision=revision.value;saving.value=true;try{const result:any=await http.post(base+`manage/libraries/${libID}/validate/`,{expected_draft_revision:draftRevision});if(session!==editSession)return;Modal.confirm({title:`确认发布 ${draft.value.title} v${baseVersion.value+1}？`,content:`包含 ${result.count ?? draft.value.items.length} 张素材。${selected.value.active?'发布后启用，贴纸馆按展示条件呈现。':'当前包已下架，发布后仍保持下架。'}历史模板固定引用保持不变。`,okText:'确认发布',cancelText:'继续编辑',onOk:()=>{if(session!==editSession||draftRevision!==revision.value||dirty.value){error.value='草稿已变化，请重新检查后发布';return Promise.reject(new Error('草稿已变化'))}return publish()}})}catch(e){fail(e)}finally{saving.value=false}}
async function publish(){if(publishIssues.value.length||dirty.value||saving.value)return;const lib={...selected.value},session=editSession;saving.value=true;try{publishKey ||= crypto.randomUUID();const result:any=await http.post(base+`manage/libraries/${lib.id}/publish/`,{expected_draft_revision:revision.value,expected_version:baseVersion.value,idempotency_key:publishKey});await load();if(session!==editSession)return;const updated=libraries.value.find(l=>l.id===lib.id)||{...lib,version:result.version};notice.value=`v${result.version} 已发布。${lib.active?'包已启用，可在客户端按展示条件获取。':'包仍为下架状态，可在列表中上架。'}历史模板绑定保持不变。`;await edit(updated)}catch(e){fail(e);throw e}finally{saving.value=false}}

function confirmLibraryAvailability(lib:any){Modal.confirm({title:lib.active?'确认下架素材包？':'确认上架素材包？',content:lib.active?'下架后停止新获取，历史作品保留。':'上架后符合展示条件的素材包将在贴纸馆展示。',onOk:()=>availability(lib)})}
async function availability(lib:any){try{await http.post(base+`manage/libraries/${lib.id}/availability/`,{expected_state_revision:lib.state_revision,active:!lib.active});await load()}catch(e){fail(e)}}
async function loadMaterials(page=materialPage.value){const token=++materialRequest;materialsLoading.value=true;try{const result:any=await http.get(base+'manage/materials/',{params:{q:materialQuery.value,type:picking.value?selected.value?.type:undefined,active:picking.value?1:undefined,paged:1,page,page_size:20}});if(token===materialRequest){materials.value=Array.isArray(result)?result:result.items;materialPage.value=Array.isArray(result)?page:result.page;materialTotal.value=Array.isArray(result)?result.length:result.total}}catch(e){if(token===materialRequest)fail(e)}finally{if(token===materialRequest)materialsLoading.value=false}}
async function showUsage(item:any){error.value='';try{const result:any=await http.get(base+`manage/materials/${item.id}/usage/`);usageRows.value=result.items;usageNote.value=result.note;usageOpen.value=true;return result}catch(e){fail(e);return null}}
async function confirmMaterialAvailability(item:any){const result=await showUsage(item);if(!result)return;Modal.confirm({title:item.active?'确认全局下架素材？':'确认恢复素材？',content:`涉及 ${result.items.length} 个当前发布包版本或模板固定版本。${result.note}`,okText:'确认',onOk:()=>materialAvailability(item)})}

async function showPicker(){picking.value=true;await loadMaterials(1)}
function addItem(item:any){if(draft.value.items.length>=500){error.value='每包最多 500 张素材';return}if(draft.value.items.some((i:any)=>itemIndex.value[i.revision]?.id===item.id))return;itemIndex.value[item.revision]=item;draft.value.items.push({revision:item.revision});dirty.value=true}
function move(i:number,delta:number){const j=i+delta;if(j<0||j>=draft.value.items.length)return;const [item]=draft.value.items.splice(i,1);draft.value.items.splice(j,0,item);dirty.value=true}
function drop(i:number){if(!permissions.can_edit||saving.value)return;if(dragIndex.value>=0){move(dragIndex.value,i-dragIndex.value);dragIndex.value=-1}}
async function uploadFiles(event:Event,purpose:string){const input=event.target as HTMLInputElement;const files=Array.from(input.files||[]);if(files.length>100){error.value='一次最多 100 个文件';input.value='';return}if(purpose==='preview'&&draft.value.previews.length+files.length>8){error.value='展示图最多 8 张';input.value='';return}if(['sticker','background'].includes(purpose)&&draft.value.items.length+files.length>500){error.value='每包最多 500 张素材';input.value='';return}const tasks=files.map(file=>reactive({file,name:file.name,purpose,state:'queued',error:'',progress:0,libraryID:selected.value.id,editSession,createdAt:Date.now()}));uploads.value.push(...tasks);input.value='';await Promise.all(tasks.map(task=>runUpload(task)))}

async function runUpload(task:any){if(task.running)return;task.running=true;await uploadLimit(async()=>{if(disposed){task.running=false;return}task.error='';try{
 if(!task.uploadID){
  if(!task.file)throw new Error('原文件未完成上传，请重新选择文件');
  task.state='processing';task.prepared ||= await prepareMaterialImage(task.file,task.purpose);
  if(disposed)return;
  if(!task.transfer || new Date(task.transfer.expires_at).getTime()<=Date.now()){
   task.transfer=await http.post(base+'manage/uploads/',{purpose:task.purpose,name:task.name,...task.prepared.metadata});
   task.originalUploaded=false;task.thumbnailUploaded=false;
  }
  task.state='uploading';
  if(!task.originalUploaded){await putImageToOSS(task.transfer.uploads.original,task.prepared.original,value=>{task.progress=Math.round(value*80)});task.originalUploaded=true}
  if(!task.thumbnailUploaded){await putImageToOSS(task.transfer.uploads.thumbnail,task.prepared.thumbnail,value=>{task.progress=80+Math.round(value*20)});task.thumbnailUploaded=true}
  task.uploadID=task.transfer.id;delete task.prepared;delete task.transfer;
  if(!task.replacement)rememberUpload(accountID.value,task);
 }
 task.state='confirming';
 const status:any=await http.post(base+`manage/uploads/${task.uploadID}/complete/`,{});
 if(status.state!=='verified'||!status.resource)throw new Error('文件确认尚未完成，请重试确认');
 if(task.replacement){task.state='verified';task.progress=100;return}
 const item=task.purpose==='sticker'||task.purpose==='background'?await http.post<unknown,any>(base+'manage/materials/',{upload_id:task.uploadID,name:task.name.replace(/\.[^.]+$/,''),kind:task.purpose==='background'?'background':'illustration',subcategory:task.purpose==='background'?'paper_texture':'object'}):null;
 if(disposed||selected.value?.id!==task.libraryID||editSession!==task.editSession)throw new Error('文件已确认并保留，请重新打开原包后重试加入草稿');
 images.value[status.resource.resource_id]=status.resource;task.attachedResource=status.resource.resource_id;
 if(task.purpose==='cover')draft.value.cover=status.resource.resource_id;
 else if(task.purpose==='preview'){if(!draft.value.previews.includes(status.resource.resource_id)){if(draft.value.previews.length>=8)throw new Error('展示图已满 8 张，请移除旧图后重试加入');draft.value.previews.push(status.resource.resource_id)}}
 else if(item){if(!draft.value.items.some((i:any)=>itemIndex.value[i.revision]?.id===item.id)){if(draft.value.items.length>=500)throw new Error('素材已保存到全局库，但本包已达 500 张上限');addItem(item)}task.attachedRevision=item.revision}
 dirty.value=true;task.state='verified';task.progress=100;rememberUpload(accountID.value,task);
 }catch(e:any){task.state='failed';task.error=e.message || '上传失败，请重试'}finally{task.running=false}})}

async function history(lib:any){historyLibrary.value=lib;try{versions.value=await http.get(base+`manage/libraries/${lib.id}/versions/`);showHistory.value=true}catch(e){fail(e)}}
async function restore(version:number){try{const d:any=await http.get(base+`manage/libraries/${historyLibrary.value.id}/draft/`);await http.post(base+`manage/libraries/${historyLibrary.value.id}/restore-draft/`,{version,expected_draft_revision:d.revision});showHistory.value=false;await edit(historyLibrary.value)}catch(e){fail(e)}}
async function loadAudit(){try{logs.value=await http.get(base+'manage/audit-logs/')}catch(e){fail(e)}}
function editMaterial(item:any){replacementUpload.value=null;editingMaterial.value=JSON.parse(JSON.stringify(item));editingCategory.value=item.kind+'/'+item.subcategory}
async function saveMaterial(){if(replacementUpload.value&&replacementUpload.value.state!=='verified'){error.value='请等待替换文件上传确认完成';return}try{const m=editingMaterial.value;const [kind,subcategory]=editingCategory.value.split('/');await http.post(base+`manage/materials/${m.id}/revisions/`,{revision:m.revision,name:m.name,keywords:m.keywords,aliases:m.aliases,kind,subcategory,upload_id:replacementUpload.value?.state==='verified'?replacementUpload.value.uploadID:undefined});editingMaterial.value=null;await loadMaterials()}catch(e){fail(e)}}
async function materialAvailability(item:any){try{await http.post(base+`manage/materials/${item.id}/availability/`,{active:!item.active,expected_active:item.active});await loadMaterials()}catch(e){fail(e)}}

async function loadDictionary(){try{dictionaryRows.value=await http.get(base+`manage/${dictionaryTarget.value}/`)}catch(e){fail(e)}}
async function saveDictionary(){try{await http.post(base+`manage/${dictionaryTarget.value}/`,dictionaryEdit.value);dictionaryEdit.value=null;await loadDictionary();categories.value=await http.get(base+'categories/')}catch(e){fail(e)}}
function toggleItem(id:number){selectedItems.value=selectedItems.value.includes(id)?selectedItems.value.filter(i=>i!==id):[...selectedItems.value,id]}
function selectAllItems(){selectedItems.value=selectedItems.value.length?[]:draft.value.items.map((i:any)=>i.revision)}
async function applyBatchCategory(){const [kind,subcategory]=batchCategory.value.split('/');for(const id of [...selectedItems.value]){const m=itemIndex.value[id];try{const updated:any=await http.post(base+`manage/materials/${m.id}/revisions/`,{revision:id,kind,subcategory});const member=draft.value.items.find((i:any)=>i.revision===id);if(member){member.revision=updated.revision;itemIndex.value[updated.revision]=updated;dirty.value=true}selectedItems.value=selectedItems.value.filter(i=>i!==id)}catch(e){fail(e)}}}
function reloadDraft(){if(dirty.value){Modal.confirm({title:'重新加载会放弃未保存的修改，确认继续？',onOk:()=>edit(selected.value)})}else void edit(selected.value)}
async function replaceMaterialFile(event:Event){const file=(event.target as HTMLInputElement).files?.[0];if(!file)return;const task=reactive({file,name:file.name,purpose:editingMaterial.value.kind==='background'?'background':'sticker',state:'queued',error:'',progress:0,replacement:true});replacementUpload.value=task;await runUpload(task)}
function beforeUnload(e:BeforeUnloadEvent){if(dirty.value||uploads.value.some(t=>t.running||t.state==='queued')){e.preventDefault();e.returnValue=''}}
watch([filterType,filterOrigin,filterState],()=>load(1));
watch(tab,t=>{if(t==='items')loadMaterials();if(t==='audit')loadAudit();if(t==='dictionary')loadDictionary();if(t==='lifecycle')lifecycle.value?.refresh()});
watch(draft,()=>{
 if(!dirty.value||saving.value||!selected.value)return;
 clearTimeout(autoSaveTimer);autoSaveTimer=setTimeout(()=>{if(dirty.value&&!saving.value)void save()},1200);
},{deep:true});
onMounted(async()=>{window.addEventListener('beforeunload',beforeUnload);await Promise.allSettled([load(),(async()=>{try{categories.value=await http.get(base+'categories/')}catch(e){fail(e)}})(),(async()=>{try{const result:any=await http.get(base+'manage/options/');if(!Array.isArray(result)){Object.assign(permissions,result);uploadEnabled.value=result.uploads_enabled;uploadUnavailableReason.value=result.upload_unavailable_reason || '';accountID.value=String(result.user_id)}}catch(e){uploadEnabled.value=false;fail(e)}})()])});
onBeforeUnmount(()=>{disposed=true;clearTimeout(autoSaveTimer);window.removeEventListener('beforeunload',beforeUnload)});
</script>
<style scoped>
.materials{display:grid;gap:16px;min-width:0}.materials :deep(.ant-space){max-width:100%}.materials :deep(.ant-table-cell){vertical-align:middle}.materials :deep(.ant-table-thead th){white-space:nowrap}.page-heading h1{margin:0}.page-heading p,.upload-help{color:#64748b}.pack-summary{display:flex;align-items:center;gap:12px}.missing-cover{display:flex;align-items:center;justify-content:center;flex-shrink:0;width:64px;height:64px;background:#f1f5f9;color:#64748b;font-size:12px;border-radius:8px}small{display:block;color:#64748b;margin-top:4px}.draft-badge{color:#b45309}.editor-footer{position:sticky;bottom:0;background:white;padding:12px 0;border-top:1px solid #eee;z-index:2}.phone{max-width:360px;margin:auto}.phone>img{width:100%;height:auto}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.grid img{width:100%;aspect-ratio:1;object-fit:contain}input[type=file]{max-width:230px}code{white-space:pre-wrap}
</style>
