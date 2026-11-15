<template>
<section><header><h1>分享邀请与奖励</h1><a-space><a-button @click="load">刷新</a-button><a-button type="primary" @click="edit()">新建活动</a-button></a-space></header>
<a-alert v-if="error" :message="error" type="error" show-icon/>
<a-tabs v-model:activeKey="tab">
<a-tab-pane key="campaigns" tab="活动配置"><a-table :data-source="data.campaigns" :columns="campaignColumns" row-key="id" :loading="busy"><template #bodyCell="{column,record}"><template v-if="column.key==='actions'"><a-button @click="edit(record)">编辑</a-button><a-button @click="mutate({action:'automation',id:record.id})">{{record.automatic?'关闭自动发放':'启用自动发放'}}</a-button><a-button @click="mutate({action:'toggle',id:record.id})">{{record.active?'暂停':'发布'}}</a-button></template></template></a-table></a-tab-pane>
<a-tab-pane key="participants" tab="邀请统计"><a-table :data-source="data.participants" :columns="participantColumns" row-key="token" :scroll="{x:800}"/></a-tab-pane>
<a-tab-pane key="rewards" tab="奖励发放"><p>只有 App 验证登录／绑定确认的邀请才计入进度。重复发放会返回原结果。</p><a-table :data-source="data.rewards" :columns="rewardColumns" row-key="id"><template #bodyCell="{column,record}"><template v-if="column.key==='actions'"><a-button v-if="!record.issued_at" @click="mutate({action:'issue',reward_id:record.id})">发放奖励</a-button><span v-else>已到账</span></template></template></a-table></a-tab-pane>
<a-tab-pane key="cards" tab="重置卡"><a-table :data-source="data.cards" :columns="cardColumns" row-key="id"><template #bodyCell="{column,record}"><template v-if="column.key==='actions'"><a-button v-if="record.status==='available'" danger @click="mutate({action:'revoke_card',card_id:record.id})">撤销</a-button></template></template></a-table></a-tab-pane>
<a-tab-pane key="audit" tab="操作审计"><a-table :data-source="data.audit" :columns="auditColumns" row-key="id" :scroll="{x:900}"/></a-tab-pane>
</a-tabs>
<p>当前展示最近 100 个活动、200 位参与者及 200 条奖励；参与人数为实际 App 验证账号数。</p>
<a-drawer v-model:open="open" title="新建邀请活动" width="min(560px,100vw)">
<a-alert v-if="error" :message="error" type="error"/><a-form :model="form" layout="vertical" @finish="save">
<a-form-item label="活动名称"><a-input v-model:value="form.title" required/></a-form-item>
<a-form-item label="开始时间"><input v-model="starts" type="datetime-local" required/></a-form-item><a-form-item label="结束时间"><input v-model="ends" type="datetime-local" required/></a-form-item>
<a-form-item label="App Store 官方产品链接"><a-input v-model:value="form.download_url" placeholder="https://apps.apple.com/…/id…" required/></a-form-item>
<a-form-item label="关联标准印制活动"><a-select v-model:value="form.print_campaign" :options="data.print_campaigns.map(p=>({value:p.id,label:p.title}))"/></a-form-item>
<a-form-item label="参与名额（每人预留 5 人半价和 10 人免费奖励）"><a-input-number v-model:value="form.participant_limit" :min="1"/></a-form-item>
<a-form-item label="登记有效天数"><a-input-number v-model:value="form.attribution_days" :min="1" :max="30"/></a-form-item>
<a-form-item label="每有效邀请奖励重置卡张数（0 为不发卡）"><a-input-number v-model:value="form.cards_per_invite" :min="0" :max="10"/></a-form-item>
<a-form-item label="每人最多奖励前多少位邀请"><a-input-number v-model:value="form.card_invite_limit" :min="1" :max="100"/></a-form-item>
<a-form-item label="重置卡有效天数"><a-input-number v-model:value="form.card_days" :min="1" :max="365"/></a-form-item>
<a-form-item label="自动发放"><a-switch v-model:checked="form.automatic"/></a-form-item>
<a-form-item label="对用户展示的完整规则（含规格、运费、两档分别发券及有效期）"><a-textarea v-model:value="form.rules" :rows="6" required/></a-form-item>
<a-alert message="先保存草稿，检查标准装订范围与成本后再发布。已有参与者的活动规则不可修改。" type="info"/>
<a-button html-type="submit" type="primary" :loading="busy">保存草稿</a-button>
</a-form></a-drawer>
</section>
</template>
<script setup lang="ts">
import {ref,reactive} from 'vue';import http from '../api/http';import {Modal} from 'ant-design-vue';
type Data={cards:Record<string,unknown>[];campaigns:Record<string,unknown>[];participants:Record<string,unknown>[];rewards:Record<string,unknown>[];audit:Record<string,unknown>[];print_campaigns:{id:number;title:string}[]}
const data=ref<Data>({cards:[],campaigns:[],participants:[],rewards:[],audit:[],print_campaigns:[]});const tab=ref('campaigns'),open=ref(false),busy=ref(false),error=ref(''),starts=ref(''),ends=ref('');
const form=reactive({id:undefined as number|undefined,title:'',download_url:'',print_campaign:undefined as number|undefined,participant_limit:100,attribution_days:7,cards_per_invite:0,card_invite_limit:10,card_days:30,automatic:false,rules:'',active:false});
const cols=(a:string[][])=>a.map(([title,dataIndex])=>({title,dataIndex}));
const campaignColumns=[...cols([['ID','id'],['活动','title'],['开放','active'],['自动发放','automatic'],['结束时间','ends_at']]),{title:'操作',key:'actions'}];
const participantColumns=cols([['账号','owner_id'],['活动','campaign_id'],['登记人数','registrations'],['有效邀请','count'],['邀请标识','token']]);
const rewardColumns=[...cols([['账号','link__owner_id'],['类型','kind'],['人数门槛','threshold'],['数量','quantity'],['到账时间','issued_at']]),{title:'操作',key:'actions'}];
const cardColumns=[...cols([['账号','owner_id'],['卡号','id'],['状态','status'],['到期','expires_at'],['来源','grant_key']]),{title:'操作',key:'actions'}];
function edit(record?:Record<string,unknown>){error.value='';Object.assign(form,{id:undefined,title:'',download_url:'',print_campaign:undefined,participant_limit:100,attribution_days:7,cards_per_invite:0,card_invite_limit:10,card_days:30,automatic:false,rules:'',active:false});starts.value='';ends.value='';if(record){Object.assign(form,record);const local=(v:unknown)=>{const d=new Date(String(v));return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)};starts.value=local(record.starts_at);ends.value=local(record.ends_at)}open.value=true}
const auditColumns=cols([['操作者','actor_id'],['操作','action'],['对象','target'],['原因','reason'],['时间','created_at']]);
const url='/api/admin/v1/experience/invitations/';
async function load(){busy.value=true;error.value='';try{data.value=await http.get(url) as unknown as Data}catch(e){error.value=String(e)}finally{busy.value=false}}
async function submit(payload:object){busy.value=true;try{await http.post(url,payload);open.value=false;await load()}catch(e){error.value=String(e)}finally{busy.value=false}}
function mutate(payload:object){const reason=window.prompt('请输入本次操作原因');if(!reason?.trim())return;Modal.confirm({title:'确认执行此操作？',content:'奖励将实际发到用户账户，重复操作不会重复发放。',onOk:()=>submit({...payload,reason})})}
async function save(){if(!starts.value||!ends.value||!form.print_campaign){error.value='请完整填写活动时间与印制活动';return}await submit({action:'save',reason:'创建邀请活动草稿',campaign:{...form,starts_at:new Date(starts.value).toISOString(),ends_at:new Date(ends.value).toISOString()}})}
void load();
</script>
<style scoped>header{display:flex;justify-content:space-between;align-items:center}input[type=datetime-local]{padding:8px;border:1px solid #bbb;border-radius:6px;width:100%}</style>
