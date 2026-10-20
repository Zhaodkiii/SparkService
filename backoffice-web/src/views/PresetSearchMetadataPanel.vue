<template>
 <section class="search-admin">
  <a-alert type="info" show-icon message="逐跨页维护搜索信息。保存为草稿，发布后生效；地点、主题与关键词只作用于选定跨页。" />
  <a-alert v-if="error" type="error" :message="error" show-icon />
  <a-space wrap class="actions">
   <a-select v-if="!templateId" v-model:value="chosen" show-search :options="books.map(b=>({value:b.id,label:b.title}))" :filter-option="filterOption" placeholder="选择手帐" style="width:260px" @change="run(load)" />
   <a-button @click="run(load)">刷新</a-button>
   <a-button @click="taxonOpen=true">地点与标签词典</a-button>
   <template v-if="id">
    <a-button key="generate-pairs" v-if="!units.length" @click="initialize">生成待确认配对</a-button>
    <a-button key="save-search-draft" :loading="busy" :disabled="!dirty" @click="run(save)">保存草稿</a-button>
    <a-button key="publish-search-metadata" type="primary" :loading="busy" @click="publish">保存并发布</a-button>
    <a-button key="discard-search-draft" @click="discard">放弃草稿</a-button>
   </template>
   <a-tag :color="dirty?'orange':'blue'">{{dirty?'有未保存修改':'工作修订 '+revision}}</a-tag>
  </a-space>
  <a-card v-if="!templateId" title="全库跨页">
   <a-space><a-input-search v-model:value="globalQuery" placeholder="查找跨页、所属本或标签"/><a-button :disabled="!globalSelected.length" @click="globalBatch=true;batchOpen=true">批量维护 {{globalSelected.length}} 项</a-button></a-space>
   <a-table :data-source="globalFiltered" :columns="[{title:'跨页',dataIndex:'title'},{title:'所属本',dataIndex:'book_title'},{title:'操作',key:'edit'}]" :row-key="(r:any)=>r.template_id+':'+r.id" :row-selection="{selectedRowKeys:globalSelected,onChange:(keys:any[])=>globalSelected=keys.map(String)}" :pagination="{pageSize:10}">
    <template #bodyCell="{column,record}"><a-button v-if="column.key==='edit'" type="link" @click="chosen=record.template_id;run(load)">维护搜索信息</a-button></template>
   </a-table>
  </a-card>
  <template v-if="id">
   <a-space wrap class="actions">
    <span>默认地点范围</span><a-select v-model:value="metadata.locationScope" :options="[{value:'mixed',label:'多地点/无统一城市'},{value:'single_city',label:'确认全本为同一城市'}]" @change="dirty=true" style="width:200px" />
    <a-select v-model:value="metadata.defaultLocationIDs" mode="multiple" :options="options('location')" placeholder="默认城市" style="min-width:200px" @change="dirty=true" />
   </a-space>
   <a-collapse><a-collapse-panel key="roles" header="页面角色与手工配对">
    <div v-for="p in pages" :key="p.id" class="role-row"><span>{{p.title}}</span><a-select v-if="pageMetadata[p.id]" v-model:value="pageMetadata[p.id].contentRole" :options="roles" @change="dirty=true" style="width:140px" /></div>
    <a-space wrap><a-select v-model:value="left" :options="pageOptions" placeholder="左页" style="width:240px"/><a-select v-model:value="right" :options="pageOptions" placeholder="右页" style="width:240px"/><a-button @click="pair">组合所选单页</a-button></a-space>
   </a-collapse-panel></a-collapse>
   <a-space wrap class="actions">
    <a-input-search v-model:value="query" placeholder="查找跨页名称、关键词或标签" allow-clear style="width:280px"/>
    <a-select v-model:value="stateFilter" :options="[{value:'all',label:'全部状态'},{value:'pending',label:'待确认'},{value:'missing',label:'缺关键词/标签'},{value:'enabled',label:'已开启搜索'}]" style="width:160px"/>
    <span>已选 {{selected.length}} 项</span><a-button :disabled="!selected.length" @click="globalBatch=false;batchOpen=true">批量维护</a-button>
   </a-space>
   <div v-for="u in filtered" :key="u.id" class="unit">
    <a-checkbox :checked="selected.includes(u.id)" @change="toggle(u.id)" />
    <div class="pair"><img v-for="p in members(u)" :key="p.id" :src="p.thumbnail" :alt="p.title" loading="lazy"/></div>
    <div class="fields">
     <a-input v-model:value="u.title" :maxlength="200" @change="dirty=true"/>
     <a-space wrap><a-tag>{{u.kind==='spread'?'跨页':u.kind==='cover'?'封面':'单页'}}</a-tag><a-tag v-if="reason(u)" color="orange">{{reason(u)}}</a-tag><span v-else>具备跨页资格</span>
      <a-button v-if="u.kind==='spread'" size="small" @click="split(u)">拆为单页</a-button>
      <a-checkbox :checked="u.pairingSource==='explicit'" @change="u.pairingSource=$event.target.checked?'explicit':'suggested'; if(u.pairingSource!=='explicit')u.searchEnabled=false;dirty=true">已核实配对/内容</a-checkbox>
      <a-switch v-model:checked="u.searchEnabled" :disabled="!!reason(u)" checked-children="参与搜索" un-checked-children="不参与搜索" @change="dirty=true"/>
     </a-space>
     <div class="field-row"><span>地点</span><a-select v-model:value="u.locationMode" :options="[{value:'none',label:'无地点'},{value:'inherit',label:'继承默认城市'},{value:'explicit',label:'指定地点'}]" @change="dirty=true" style="width:150px"/><a-select v-if="u.locationMode==='explicit'" v-model:value="u.locationIDs" mode="multiple" show-search :filter-option="filterOption" :options="options('location')" @change="dirty=true" style="flex:1"/></div>
     <div class="field-row"><span>标签</span><a-select v-model:value="u.tagIDs" mode="multiple" show-search :filter-option="filterOption" :options="terms.filter(t=>t.dimension!=='location'&&t.active).map(t=>({value:t.id,label:dimensionName(t.dimension)+' · '+t.name}))" @change="dirty=true" style="flex:1"/></div>
     <div class="field-row"><span>关键词</span><a-select v-model:value="u.searchKeywords" mode="tags" :token-separators="[',','，','\n']" placeholder="回车添加；最多10项，每项30字" @change="dirty=true" style="flex:1"/></div>
    </div>
   </div>
   <a-empty v-if="!filtered.length" description="暂无阅读单元，请上传页面或生成待确认配对"/>
   <a-card title="发布前试搜" class="actions"><a-space><a-input v-model:value="testQuery" placeholder="苏州 / 园林 / 狮子林"/><a-button :loading="busy" @click="trial">保存草稿并试搜</a-button></a-space><div v-if="testResult"><p>{{testResult.total}} 个命中</p><div v-for="entry in testResult.entries" :key="entry.id">{{entry.title}} · {{entry.matched_fields.map((f:any)=>f.term+'：'+f.field+' / '+f.source).join('；')}}</div></div></a-card>
  </template>
  <a-modal v-model:open="batchOpen" title="批量维护选中跨页" @ok="applyBatch">
   <p>只影响明确选中的 {{globalBatch?globalSelected.length:selected.length}} 项，保存为草稿。</p><a-select v-model:value="batchField" :options="[{value:'tagIDs',label:'标签'},{value:'searchKeywords',label:'关键词'},{value:'locationIDs',label:'地点'}]"/><a-select v-model:value="batchOperation" :options="[{value:'add',label:'合并添加'},{value:'remove',label:'移除'},{value:'replace',label:'完整替换（覆盖原值）'}]"/>
   <a-select v-model:value="batchValues" :mode="batchField==='searchKeywords'?'tags':'multiple'" :options="batchField==='locationIDs'?options('location'):terms.filter(t=>t.dimension!=='location').map(t=>({value:t.id,label:t.name}))" style="width:100%;margin-top:16px"/>
  </a-modal>
  <a-drawer v-model:open="taxonOpen" title="地点与标签词典" width="620">
   <a-alert message="地点父级用于城市召回；标签别名用于繁简、拼音等受控表达。停用不删除已有关联。"/>
   <a-list :data-source="terms"><template #renderItem="{item}"><a-list-item><span>{{dimensionName(item.dimension)}} · {{item.name}} · {{item.aliases.join(' / ')}}</span><a-space><a-button size="small" @click="editTaxon(item)">编辑</a-button><a-button size="small" :disabled="!!item.merged_into" @click="mergeSource=item.id;mergeOpen=true">合并</a-button></a-space></a-list-item></template></a-list>
   <a-form layout="vertical"><a-form-item label="稳定标识"><a-input v-model:value="term.id" :disabled="editingTerm" placeholder="如 loc-suzhou"/></a-form-item><a-form-item label="维度"><a-select v-model:value="term.dimension" :disabled="editingTerm" :options="['location','theme','style','usage'].map(v=>({value:v,label:dimensionName(v)}))"/></a-form-item><a-form-item label="名称"><a-input v-model:value="term.name"/></a-form-item><a-form-item label="别名"><a-select v-model:value="term.aliases" mode="tags" :token-separators="[',','，']"/></a-form-item><a-form-item v-if="term.dimension==='location'" label="父地点"><a-select v-model:value="term.parent" allow-clear :options="options('location').filter(t=>t.value!==term.id)"/></a-form-item><a-form-item label="启用"><a-switch v-model:checked="term.active"/></a-form-item><a-space><a-button type="primary" @click="saveTerm">保存词项</a-button><a-button @click="newTerm">新增</a-button></a-space></a-form>
  </a-drawer>
  <a-modal v-model:open="mergeOpen" title="合并词项" @ok="mergeTerm"><p>旧名称保留为目标别名，历史版本不改写。请先核对影响范围。</p><a-select v-model:value="mergeTarget" :options="terms.filter(t=>t.id!==mergeSource&&t.dimension===terms.find(t=>t.id===mergeSource)?.dimension&&t.active&&!t.merged_into).map(t=>({value:t.id,label:t.name}))" style="width:100%"/></a-modal>
 </section>
</template>
<script setup lang="ts">
import {computed,ref,watch,onMounted} from 'vue';
import {message,Modal} from 'ant-design-vue';
import http from '../api/http';
const props=defineProps<{templateId?:string}>();const emit=defineEmits<{changed:[]}>();
interface Unit {id:string;kind:string;title:string;position:number;leftPageID:string|null;rightPageID:string|null;pairingSource:string;searchEnabled:boolean;locationMode:string;locationIDs:string[];tagIDs:string[];searchKeywords:string[]}
interface Page {id:string;title:string;thumbnail:string;preview:string}
interface Term {id:string;dimension:string;name:string;aliases:string[];parent:string|null;active:boolean;merged_into?:string|null}
const base='/api/admin/v1/diary-presets/';
const chosen=ref(''),books=ref<{id:string;title:string}[]>([]),units=ref<Unit[]>([]),pages=ref<Page[]>([]),terms=ref<Term[]>([]),revision=ref(0),dirty=ref(false),busy=ref(false),error=ref('');
const metadata=ref<{locationScope:string;defaultLocationIDs:string[]}>({locationScope:'mixed',defaultLocationIDs:[]});
const pageMetadata=ref<Record<string,{contentRole:string;displayTitle?:string}>>({});
const id=computed(()=>props.templateId||chosen.value),query=ref(''),stateFilter=ref('all'),left=ref<string>(),right=ref<string>();
const selected=ref<string[]>([]),batchOpen=ref(false),batchField=ref('tagIDs'),batchOperation=ref('add'),batchValues=ref<string[]>([]),taxonOpen=ref(false);
const testQuery=ref(''),testResult=ref<any>(),editingTerm=ref(false);
const globalRows=ref<any[]>([]),globalSelected=ref<string[]>([]),globalQuery=ref(''),globalBatch=ref(false),mergeOpen=ref(false),mergeSource=ref(''),mergeTarget=ref<string>();
const globalFiltered=computed(()=>globalRows.value.filter(r=>r.kind==='spread'&&JSON.stringify([r.title,r.book_title,r.searchKeywords,(r.tagIDs||[]).map((id:string)=>terms.value.find(t=>t.id===id)?.name)]).includes(globalQuery.value)));
const blankTerm=():Term=>({id:'',dimension:'theme',name:'',aliases:[],parent:null,active:true});const term=ref<Term>(blankTerm());
const roles=[{value:'front_cover',label:'封面'},{value:'back_cover',label:'封底'},{value:'shell',label:'外壳'},{value:'content',label:'正文'},{value:'blank',label:'空白占位'}];
const dimensionName=(d:string)=>({location:'地点',theme:'主题',style:'风格',usage:'用途'}[d]||d);
const filterOption=(input:string,option:any)=>String(option.label).toLowerCase().includes(input.toLowerCase());
const options=(d:string)=>terms.value.filter(t=>t.dimension===d&&t.active).map(t=>({value:t.id,label:t.name+(t.aliases.length?' / '+t.aliases.join(' / '):'')}));
const pageOptions=computed(()=>pages.value.map(p=>({value:p.id,label:p.title})));
function members(u:Unit){return [u.leftPageID,u.rightPageID].filter(Boolean).map(id=>pages.value.find(p=>p.id===id)!).filter(Boolean)}
function reason(u:Unit){return u.kind!=='spread'||!u.leftPageID||!u.rightPageID?'仅完整双页可搜索':u.pairingSource!=='explicit'?'配对待确认':members(u).some(p=>pageMetadata.value[p.id]?.contentRole!=='content')?'含非正文页面':''}
const filtered=computed(()=>units.value.filter(u=>(!query.value||JSON.stringify([u.title,u.searchKeywords,u.tagIDs.map(id=>terms.value.find(t=>t.id===id)?.name)]).includes(query.value))&&(stateFilter.value==='all'||stateFilter.value==='pending'&&u.pairingSource!=='explicit'||stateFilter.value==='missing'&&!u.tagIDs.length&&!u.searchKeywords.length||stateFilter.value==='enabled'&&u.searchEnabled)));
async function run(fn:()=>Promise<void>){busy.value=true;error.value='';try{await fn()}catch(e){error.value=e instanceof Error?e.message:String(e);message.error(error.value)}finally{busy.value=false}}
async function load(){terms.value=await http.get(base+'tags/');if(!props.templateId)globalRows.value=await http.get(base+'reading-units/');if(!id.value)return;const data:any=await http.get(base+`templates/${id.value}/reading-units/`);revision.value=data.revision;units.value=data.manifest.readingUnits||[];metadata.value=data.manifest.metadata||{locationScope:'mixed',defaultLocationIDs:[]};pageMetadata.value=data.manifest.pageMetadata||{};pages.value=data.pages;dirty.value=false;selected.value=[];testResult.value=undefined}
async function initialize(){await run(async()=>{await http.post(base+`templates/${id.value}/suggest-reading-units/`,{revision:revision.value});await load();emit('changed')})}
async function save(){if(!id.value)return;units.value.forEach((u,i)=>{u.position=i;if(reason(u))u.searchEnabled=false;u.searchKeywords=Array.from(new Set(u.searchKeywords.map(w=>w.trim()).filter(Boolean)))});const data:any=await http.put(base+`templates/${id.value}/reading-units/`,{revision:revision.value,readingUnits:units.value,pageMetadata:pageMetadata.value,metadata:metadata.value});revision.value=data.revision;dirty.value=false;emit('changed')}
function publish(){run(async()=>{await save();const data:any=await http.post(base+`templates/${id.value}/publish/`,{revision:revision.value});revision.value=data.revision;message.success(`已发布 ${data.searchable_spread_count} 个可搜索跨页`);emit('changed')})}
function discard(){Modal.confirm({title:'放弃未发布草稿？',content:'本次会恢复该本全部已发布内容，包括页面编排。',onOk:()=>run(async()=>{await http.post(base+`templates/${id.value}/discard-search-draft/`,{revision:revision.value});await load();emit('changed')})})}
async function trial(){await run(async()=>{if(dirty.value)await save();testResult.value=await http.post(base+`templates/${id.value}/search-preview/`,{revision:revision.value,kind:'spread',q:testQuery.value})})}
function toggle(key:string){selected.value=selected.value.includes(key)?selected.value.filter(k=>k!==key):[...selected.value,key]}
async function applyBatch(){if(globalBatch.value){await run(async()=>{const groups=new Map<string,{template_id:string;revision:number;unit_ids:string[]}>();for(const row of globalRows.value.filter(r=>globalSelected.value.includes(r.template_id+':'+r.id))){const g:{template_id:string;revision:number;unit_ids:string[]}=groups.get(row.template_id)||{template_id:row.template_id,revision:row.revision,unit_ids:[]};g.unit_ids.push(row.id);groups.set(row.template_id,g)}const response:any=await http.post(base+'reading-units/batch-search-metadata/',{templates:[...groups.values()],field:batchField.value,operation:batchOperation.value,values:batchValues.value});const failed=response.results.filter((r:any)=>!r.ok);if(failed.length)message.warning(failed.map((r:any)=>r.error).join('；'));else message.success('已保存草稿，请逐本试搜并发布');await load();batchOpen.value=false});return}for(const u of units.value.filter(u=>selected.value.includes(u.id))){const key=batchField.value as 'tagIDs'|'searchKeywords'|'locationIDs';u[key]=batchOperation.value==='add'?[...new Set([...u[key],...batchValues.value])]:batchOperation.value==='remove'?u[key].filter(v=>!batchValues.value.includes(v)):[...batchValues.value];if(key==='locationIDs')u.locationMode='explicit'}dirty.value=true;batchOpen.value=false}
function split(u:Unit){const i=units.value.indexOf(u);units.value.splice(i,1,...members(u).map(p=>({...u,id:crypto.randomUUID(),kind:'single',title:p.title,leftPageID:null,rightPageID:p.id,searchEnabled:false,pairingSource:'suggested'})));dirty.value=true}
function pair(){if(!left.value||!right.value||left.value===right.value){message.warning('请选择不同左右页');return}const positions=[left.value,right.value].map(id=>pages.value.findIndex(p=>p.id===id));if(positions[1]!==positions[0]!+1){message.warning('左右页必须按原始顺序相邻');return}const affected=units.value.filter(u=>[u.leftPageID,u.rightPageID].some(p=>p===left.value||p===right.value));if(affected.some(u=>u.kind==='spread')){message.warning('请先拆分原跨页再重新组合');return}const first=units.value.indexOf(affected[0]!);units.value=units.value.filter(u=>!affected.includes(u));units.value.splice(first,0,{id:crypto.randomUUID(),kind:'spread',title:'新跨页',position:first,leftPageID:left.value,rightPageID:right.value,pairingSource:'suggested',searchEnabled:false,locationMode:'none',locationIDs:[],tagIDs:[],searchKeywords:[]});dirty.value=true}
async function mergeTerm(){await run(async()=>{if(!mergeTarget.value)return;await http.post(base+`tags/${mergeSource.value}/merge/`,{target_id:mergeTarget.value});terms.value=await http.get(base+'tags/');mergeOpen.value=false;message.success('词项已合并')})}
function editTaxon(t:Term){term.value=JSON.parse(JSON.stringify(t));editingTerm.value=true}function newTerm(){term.value=blankTerm();editingTerm.value=false}
async function saveTerm(){await run(async()=>{if(editingTerm.value)await http.patch(base+`tags/${term.value.id}/`,term.value);else await http.post(base+'tags/',term.value);terms.value=await http.get(base+'tags/');newTerm();message.success('词典已保存')})}
onMounted(()=>run(async()=>{if(!props.templateId)books.value=await http.get(base+'templates/');await load()}));watch(()=>props.templateId,()=>run(load));
</script>
<style scoped>
.search-admin{display:grid;gap:12px}.actions{margin:12px 0}.unit{display:flex;align-items:flex-start;gap:12px;border:1px solid #e5e5e5;border-radius:10px;padding:14px}.pair{display:flex;width:240px;flex-shrink:0;align-items:center}.pair img{width:50%;height:175px;object-fit:contain}.fields{display:grid;gap:12px;flex:1;min-width:260px}.field-row{display:flex;gap:10px;align-items:center}.role-row{display:flex;justify-content:space-between;gap:10px;margin-bottom:8px}@media(max-width:900px){.unit{flex-wrap:wrap}.pair{width:200px}.fields{width:100%}}
</style>
