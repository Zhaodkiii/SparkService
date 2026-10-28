<script setup lang="ts">
import { ref,onMounted } from 'vue';
import http from '../../api/http';
import { useAuthStore } from '../../stores/auth';
const auth=useAuthStore(),items=ref<any[]>([]),cases=ref<any[]>([]),reason=ref(''),selected=ref<string>(),busy=ref(false),error=ref('');
async function load(){busy.value=true;error.value='';try{const r=await http.get<{items:any[];cases:any[]},{items:any[];cases:any[]}>('/api/v1/billing/manage/operations/');items.value=r.items;cases.value=r.cases;}catch(e){error.value=e instanceof Error?e.message:String(e);}finally{busy.value=false;} }
async function compensate(){if(!selected.value||!reason.value.trim())return;busy.value=true;try{await http.post(`/api/v1/billing/manage/operations/${selected.value}/compensate/`,{reason:reason.value.trim()});selected.value=undefined;reason.value='';await load();}catch(e){error.value=e instanceof Error?e.message:String(e);}finally{busy.value=false;} }
onMounted(load);
</script>
<template>
<a-alert v-if="error" type="error" :message="error" show-icon />
<p>结果未知的扣钻需保留原交易核查；只有确认成功的扣钻可申请补偿。制作已开始的定制须进入人工售后。</p>
<a-button :loading="busy" @click="load">刷新交易与异常</a-button>
<a-table row-key="id" :data-source="items" :columns="[{title:'操作单',dataIndex:'id'},{title:'类型',dataIndex:'kind'},{title:'钻石变动',dataIndex:'delta'},{title:'状态',dataIndex:'state'},{title:'尝试次数',dataIndex:'attempt_count'},{title:'操作',key:'action'}]">
<template #bodyCell="{column,record}"><a-button v-if="column.key==='action'&&record.kind==='debit'&&record.state==='succeeded'&&auth.hasPermission('billing.resolve_refund')" @click="selected=record.id">申请钻石补偿</a-button></template>
</a-table>
<a-table row-key="id" :data-source="cases" :columns="[{title:'待核查事项',dataIndex:'kind'},{title:'操作单',dataIndex:'operation_id'},{title:'创建时间',dataIndex:'created_at'}]" />
<a-modal :open="!!selected" title="钻石补偿" :confirm-loading="busy" :ok-button-props="{disabled:!reason.trim()}" @cancel="selected=undefined" @ok="compensate">
<p>确认后撤销本单授予的内容许可，并向原钱包返还已确认扣除的钻石。此操作会记录操作员与原因。</p>
<a-textarea v-model:value="reason" :maxlength="500" placeholder="必须填写补偿原因" />
</a-modal>
</template>
