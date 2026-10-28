<script setup lang="ts">
import { ref,onMounted } from 'vue';
import http from '../../api/http';
import { useAuthStore } from '../../stores/auth';
const auth=useAuthStore(),items=ref<any[]>([]),busy=ref(false),error=ref('');
const form=ref({code:'',title:'',expected_revision:0,standard_diamonds:null as number|null,pro_diamonds:null as number|null,included_pages:12,max_photos:30,included_revision_rounds:1,lead_workdays:3,terms_version:'custom-digital-v1'});
async function load(){if(!auth.hasPermission('billing.publish_pricing'))return;try{items.value=(await http.get<{items:any[]},{items:any[]}>('/api/v1/billing/manage/customization-packages/')).items;}catch(e){error.value=e instanceof Error?e.message:String(e);} }
function edit(p:any){form.value={code:p.package__code,title:p.package__title,expected_revision:p.revision,standard_diamonds:p.standard_diamonds,pro_diamonds:p.pro_diamonds,included_pages:p.included_pages,max_photos:p.max_photos,included_revision_rounds:p.included_revision_rounds,lead_workdays:p.lead_workdays,terms_version:'custom-digital-v1'};}
async function save(){busy.value=true;error.value='';try{await http.post('/api/v1/billing/manage/customization-packages/',form.value);await load();form.value.expected_revision+=1;}catch(e){error.value=e instanceof Error?e.message:String(e);}finally{busy.value=false;} }
onMounted(load);
</script>
<template>
<section v-if="auth.hasPermission('billing.publish_pricing')">
<a-alert v-if="error" type="error" :message="error" show-icon />
<p>每次保存生成不可变套餐版本；已发出的报价保留原价格和范围。</p>
<a-form layout="vertical">
<a-row :gutter="16">
<a-col :span="8"><a-form-item label="套餐代码"><a-input v-model:value="form.code" placeholder="例如 travel_standard" /></a-form-item></a-col>
<a-col :span="8"><a-form-item label="套餐名称"><a-input v-model:value="form.title" /></a-form-item></a-col>
<a-col :span="8"><a-form-item label="当前版本（新套餐为 0）"><a-input-number v-model:value="form.expected_revision" :min="0" :precision="0" /></a-form-item></a-col>
<a-col :span="8"><a-form-item label="普通价格（钻石）"><a-input-number v-model:value="form.standard_diamonds" :min="1" :precision="0" /></a-form-item></a-col>
<a-col :span="8"><a-form-item label="Pro 价格（留空表示无优惠）"><a-input-number v-model:value="form.pro_diamonds" :min="1" :precision="0" /></a-form-item></a-col>
<a-col :span="8"><a-form-item label="包含页数"><a-input-number v-model:value="form.included_pages" :min="1" :max="100" :precision="0" /></a-form-item></a-col>
<a-col :span="8"><a-form-item label="最多照片数"><a-input-number v-model:value="form.max_photos" :min="1" :max="30" :precision="0" /></a-form-item></a-col>
<a-col :span="8"><a-form-item label="包含修改轮次"><a-input-number v-model:value="form.included_revision_rounds" :min="0" :max="10" :precision="0" /></a-form-item></a-col>
<a-col :span="8"><a-form-item label="预计工作日"><a-input-number v-model:value="form.lead_workdays" :min="1" :max="90" :precision="0" /></a-form-item></a-col>
</a-row>
<a-form-item label="服务条款版本"><a-input v-model:value="form.terms_version" /></a-form-item>
<a-popconfirm title="发布此固定套餐的新版本？已有报价不会变化。" @confirm="save"><a-button type="primary" :loading="busy" :disabled="!form.code||!form.title||!form.standard_diamonds">发布套餐版本</a-button></a-popconfirm>
</a-form>
<a-table row-key="id" :data-source="items" :columns="[{title:'套餐',dataIndex:'package__title'},{title:'版本',dataIndex:'revision'},{title:'普通价',dataIndex:'standard_diamonds'},{title:'Pro 价',dataIndex:'pro_diamonds'},{title:'操作',key:'action'}]">
<template #bodyCell="{column,record}"><a-button v-if="column.key==='action'" @click="edit(record)">以此版本编辑</a-button></template>
</a-table>
</section>
<p v-else>需要收费策略发布权限才能管理定制套餐。</p>
</template>
