<script setup lang="ts">
import { ref, watch } from 'vue';
import http from '../../api/http';
import { useAuthStore } from '../../stores/auth';
const props=defineProps<{requestId:string;status:string}>();
const auth=useAuthStore(), packages=ref<any[]>([]), quotes=ref<any[]>([]), fundings=ref<any[]>([]), selected=ref<string>(), busy=ref(false), error=ref('');
async function load(){ if(!auth.hasPermission('billing.publish_pricing'))return;busy.value=true;error.value='';try{const [p,q]=await Promise.all([http.get<{items:any[]},{items:any[]}>('/api/v1/billing/manage/customization-packages/'),http.get<{quotes:any[];fundings:any[]},{quotes:any[];fundings:any[]}>(`/api/v1/billing/manage/customizations/${props.requestId}/quote/`)]);packages.value=p.items;quotes.value=q.quotes;fundings.value=q.fundings;}catch(e){error.value=e instanceof Error?e.message:String(e);}finally{busy.value=false;} }
async function issue(){if(!selected.value)return;busy.value=true;try{await http.post(`/api/v1/billing/manage/customizations/${props.requestId}/quote/`,{package_revision_id:selected.value});await load();}catch(e){error.value=e instanceof Error?e.message:String(e);}finally{busy.value=false;} }
watch(()=>props.requestId,()=>{selected.value=undefined;void load();},{immediate:true});
</script>
<template>
<a-card v-if="auth.hasPermission('billing.publish_pricing')" title="钻石报价与付款" style="margin:16px 0">
  <a-alert v-if="error" type="error" :message="error" show-icon />
  <p>报价冻结本次提交资料与制作范围；用户确认并付清后才能开始制作。没有钻石报价的历史需求沿用原流程。</p>
  <a-space v-if="['submitted','needs_info'].includes(status)">
    <a-select v-model:value="selected" placeholder="选择固定套餐版本" style="width:340px" :options="packages.map(p=>({value:p.id,label:`${p.package__title} · v${p.revision} · ${p.standard_diamonds} 钻${p.pro_diamonds ? ` / Pro ${p.pro_diamonds} 钻`:''}`}))" />
    <a-popconfirm title="向用户发出此套餐范围与价格的冻结报价？" @confirm="issue"><a-button :disabled="!selected" :loading="busy">发出报价</a-button></a-popconfirm>
  </a-space>
  <a-button type="link" :loading="busy" @click="load">刷新付款状态</a-button>
  <a-table size="small" row-key="id" :data-source="quotes" :pagination="false" :columns="[{title:'报价版本',dataIndex:'revision'},{title:'普通钻石价',dataIndex:'standard_diamonds'},{title:'Pro 钻石价',dataIndex:'pro_diamonds'},{title:'有效期',dataIndex:'expires_at'}]" />
  <a-table size="small" row-key="id" :data-source="fundings" :pagination="false" :columns="[{title:'付款单',dataIndex:'id'},{title:'钻石',dataIndex:'amount'},{title:'状态',dataIndex:'status'},{title:'钱包环境',dataIndex:'identity__wallet_domain'}]" />
</a-card>
</template>
