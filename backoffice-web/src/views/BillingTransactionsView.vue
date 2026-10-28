<template>
<section class="transactions">
<header><div><h1>交易中心</h1><p>查看用户充值、会员购买、钻石消费与到账异常。</p></div><a-space><span class="muted">30 秒自动刷新</span><a-switch v-model:checked="autoRefresh"/><a-button :loading="busy" @click="load()">刷新</a-button></a-space></header>
<a-alert v-if="error" :message="error" type="error" show-icon/>
<a-alert show-icon :type="environment==='sandbox'?'warning':'info'" :message="environment==='sandbox'?'沙盒测试数据 · 不计入正式收入':'正式环境 · 金额为渠道报告的交易金额，不代表 Apple 结算收入'"/>
<div class="filters">
 <a-select v-model:value="environment" style="width:140px" @change="reset">
  <a-select-option value="production">正式环境</a-select-option>
  <a-select-option value="sandbox">沙盒环境</a-select-option>
 </a-select>
 <a-input-search v-model:value="search" placeholder="用户名 / 用户 ID / RevenueCat 用户 ID" style="width:330px" allow-clear @search="reset"/>
 <a-select v-if="isPayments" v-model:value="status" style="width:150px" @change="reset">
  <a-select-option value="all">全部交易状态</a-select-option>
  <a-select-option value="confirmed">支付已确认</a-select-option>
  <a-select-option value="refunded">已退款</a-select-option>
  <a-select-option v-if="section==='recharge'" value="pending_delivery">到账待确认</a-select-option>
  <a-select-option value="unknown_amount">金额待确认</a-select-option>
 </a-select>
 <a-range-picker :placeholder="['记录开始日期','记录结束日期']" v-model:value="dates" @change="reset"/>
 <a-tag v-if="account">用户 {{ account }} <a @click="account='';reset()">取消</a></a-tag>
 <a-tag v-if="identity">已筛选用户 <a @click="identity='';reset()">取消</a></a-tag>
</div>
<a-alert v-if="unlinked" type="warning" :message="`${unlinked} 条回调无法关联用户，请核查服务端事件记录`"/>
<a-alert v-if="pendingTopups" type="warning" show-icon :message="`${pendingTopups} 笔充值超过 5 分钟仍未确认到账，请在钻石充值中核查。`"/>
<a-tabs v-model:activeKey="section" @change="changeSection"><a-tab-pane key="recharge" tab="钻石充值"/><a-tab-pane key="subscription" tab="会员订阅"/><a-tab-pane key="redemption" tab="钻石消费"/><a-tab-pane key="customization" tab="定制付款"/><a-tab-pane key="users" tab="用户资产"/><a-tab-pane key="activity" tab="收款动态"/><a-tab-pane key="alerts" tab="异常提醒"/><a-tab-pane key="physical" tab="实物付款"/></a-tabs>
<template v-if="section==='physical'"><p>印制付款、渠道查询和原路退款在支付管理中处理。</p><router-link to="/print-payments">进入实物支付管理 →</router-link></template>
<template v-else>
<div v-if="isPayments" class="summary"><b>{{ total }} 笔记录</b><span v-for="s in summary.amounts" :key="s.currency">{{ s.currency }} {{ s.amount }}</span><span>金额待确认 {{ summary.unknown_amounts||0 }} 笔</span><small>按当前筛选统计，排除已确认退款；不同币种分别统计，钻石消费不重复计入收入。</small></div>
<a-table :data-source="items" :columns="columns" row-key="id" :loading="busy" :scroll="{x:1200}" :pagination="{current:page,pageSize:20,total,showSizeChanger:false}" @change="changePage">
<template #bodyCell="{column,record}">
<template v-if="column.key==='user'"><a @click="openAssets(record)">{{ record.name }}</a><div class="muted">ID {{ record.account_id }} · {{ record.environment==='sandbox'?'沙盒':'正式' }}</div></template>
<template v-else-if="column.key==='product'"><div>{{ record.expected_units ? record.expected_units+' 钻充值包' : record.product }}</div><div v-if="record.expected_units" class="muted">{{ record.product }}</div></template>
<template v-else-if="column.key==='money'">{{ money(record) }}</template>
<template v-else-if="column.key==='delivery'">{{ label(record.delivery_state) }}<div class="muted">应到账 {{ record.expected_units??'—' }} / 已确认 {{ record.verified_units??'—' }} 钻</div></template>
<template v-else-if="column.key==='status'"><a-tag>{{ label(record.payment_state||record.status) }}</a-tag></template>
<template v-else-if="column.key==='kind'">{{ label(record.kind) }}</template>
<template v-else-if="column.key==='lifecycle'">{{ label(record.lifecycle) }}</template>
<template v-else-if="column.key==='time'">{{ date(record.purchased_at||record.created_at) }}</template>
<template v-else-if="column.key==='balance'">{{ record.balance??'未确认' }}<div class="muted">{{ label(record.balance_state) }} · {{ date(record.fetched_at) }}</div></template>
<template v-else-if="column.key==='member'">到期 {{ date(record.member_until) }}<div class="muted">核验于 {{ date(record.member_verified_at) }}</div></template>
<template v-else-if="column.key==='action'"><a @click="isPayments?openPayment(record.id):openAssets(record)">{{ isPayments?'交易详情':'查看资产' }}</a></template>
</template><template #emptyText><a-empty description="当前筛选下暂无已接收记录，可切换沙盒环境或检查回调。"/></template></a-table></template>
<a-drawer v-model:open="drawer" :title="detailKind==='payment'?'交易详情':'用户资产'" :width="640" destroy-on-close><a-spin :spinning="detailBusy"><a-alert v-if="detailError" type="error" :message="detailError"/><template v-if="detail">
<h3>{{ detail.name }} · ID {{ detail.account_id }}</h3><a-tag>{{ detail.environment==='sandbox'?'沙盒':'正式' }}</a-tag><p><a :href="detail.revenuecat_url" target="_blank" rel="noopener noreferrer">查看 RevenueCat 客户 ↗</a></p>
<template v-if="detailKind==='payment'"><a-descriptions bordered :column="1"><a-descriptions-item label="商品">{{ detail.product }}</a-descriptions-item><a-descriptions-item label="交易金额">{{ money(detail) }}</a-descriptions-item><a-descriptions-item label="支付状态">{{ label(detail.payment_state) }}</a-descriptions-item><a-descriptions-item v-if="detail.kind==='recharge'" label="到账状态">{{ label(detail.delivery_state) }}</a-descriptions-item><a-descriptions-item label="渠道交易号">{{ detail.transaction_id }}</a-descriptions-item><a-descriptions-item label="购买时间">{{ date(detail.purchased_at) }}</a-descriptions-item></a-descriptions><h3>关联事件</h3><a-timeline><a-timeline-item v-for="e in detail.events" :key="e.event_id">{{ label(e.type) }} · {{ date(e.received_at) }}<div class="muted">{{ e.event_id }} · {{ e.state }} · {{ e.cancel_reason||'' }}</div></a-timeline-item></a-timeline><a-button @click="openAssets(detail)">查看用户资产与消费</a-button></template>
<template v-else><a-descriptions bordered :column="1"><a-descriptions-item label="钻石余额快照">{{ detail.balance??'未确认' }} · {{ label(detail.balance_state) }}</a-descriptions-item><a-descriptions-item label="余额同步时间">{{ date(detail.fetched_at) }}</a-descriptions-item><a-descriptions-item label="会员有效期">{{ date(detail.member_until) }}</a-descriptions-item><a-descriptions-item label="会员核验时间">{{ date(detail.member_verified_at) }}</a-descriptions-item><a-descriptions-item label="永久解锁">{{ detail.ownership_count }} 项</a-descriptions-item></a-descriptions><p>同步余额不会补发钻石，也不会自动确认待到账订单。</p><a-space wrap><a-button v-if="auth.hasPermission('billing.sync_transactions')" :loading="syncing" @click="syncAssets">同步资产快照</a-button><a-button @click="filterUser('recharge')">查看充值</a-button><a-button @click="filterUser('subscription')">查看会员交易</a-button><a-button @click="filterUser('redemption')">查看消费</a-button><a-button @click="filterUser('customization')">查看定制付款</a-button></a-space><h3>内容拥有权（最近 100 项）</h3><a-list :data-source="detail.ownerships"><template #renderItem="{item}"><a-list-item><div>{{ item.title }} · {{ label(item.state) }}<div class="muted">{{ item.target_id }}</div></div></a-list-item></template></a-list></template>
</template></a-spin></a-drawer>
</section>
</template>
<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,watch} from 'vue';
import {useRoute} from 'vue-router';
import type {Dayjs} from 'dayjs';
import http from '../api/http';
import {useAuthStore} from '../stores/auth';
const route=useRoute(),auth=useAuthStore();
const environment=ref('production'),section=ref('recharge'),search=ref(''),status=ref('all'),identity=ref(''),account=ref(String(route.query.account||'')),dates=ref<[Dayjs,Dayjs]|null>(null);
const autoRefresh=ref(true);let refreshTimer:ReturnType<typeof setInterval>|undefined;
const items=ref<any[]>([]),summary=ref<any>({}),total=ref(0),page=ref(1),pendingTopups=ref(0),unlinked=ref(0),busy=ref(false),error=ref('');
const drawer=ref(false),detail=ref<any>(null),detailKind=ref('payment'),detailBusy=ref(false),detailError=ref(''),syncing=ref(false);
let generation=0,detailGeneration=0;
const isPayments=computed(()=>['recharge','subscription'].includes(section.value));
const labels:Record<string,string>={confirmed:'支付已确认',unconfirmed:'待确认',refunded:'已退款',granted:'已到账',grant_pending:'到账待确认',purchase_observed:'已收到购买事件',refund_observed:'退款回收待确认',unknown:'待核查',fulfilled:'已解锁',prepared:'处理中',debit_unknown:'扣钻待核查',rejected:'已拒绝',compensated:'已补偿',funded:'已付钻',debit_pending:'扣钻处理中',payment_identity_conflict:'交易关联用户冲突',topup_units_mismatch:'充值到账数量异常',refund_exposure:'退款后余额与权益待核查',environment_mismatch:'交易环境不匹配',event_environment_unverified:'回调环境无法确认',open:'待处理',closed:'已关闭',processed:'已处理',pending:'待处理',quarantined:'已隔离待核查',fresh:'已同步快照',stale:'快照待更新',active:'有效',revoked:'已撤销',INITIAL_PURCHASE:'首次订阅',RENEWAL:'续费',NON_RENEWING_PURCHASE:'单次购买',RENEWAL_CANCELLED:'已取消续订（不等于到期）',REFUND_CONFIRMED:'退款已确认',VIRTUAL_CURRENCY_TRANSACTION:'钻石余额变动',CANCELLATION:'取消 / 退款事件',UNCANCELLATION:'恢复续订',EXPIRATION:'已到期',BILLING_ISSUE:'账单异常',REFUND_REVERSED:'退款撤销',SUBSCRIPTION_EXTENDED:'订阅延期'};
function label(v:string){return labels[v]||v||'—';}
function date(v:string){return v?new Date(v).toLocaleString('zh-CN'):'—';}
function money(r:any){return r.amount===null||r.amount===undefined?'金额待确认':`${r.currency} ${Number(r.amount).toLocaleString('zh-CN',{maximumFractionDigits:6})}`;}
const columns=computed(()=>{const head=[{title:'用户',key:'user',width:190}],tail=[{title:'操作',key:'action',width:110,fixed:'right' as const}];
 if(isPayments.value)return [...head,{title:'商品',key:'product',width:240},{title:'交易金额',key:'money',width:120},{title:'支付状态',key:'status',width:130},...(section.value==='recharge'?[{title:'钻石到账',key:'delivery',width:210}]:[{title:'最新事件',key:'lifecycle'}]),{title:'时间',key:'time',width:180},...tail];
 if(section.value==='users')return [...head,{title:'钻石余额快照',key:'balance',width:230},{title:'会员有效期',key:'member',width:240},...tail];
 if(['redemption','customization'].includes(section.value))return [...head,{title:'内容',dataIndex:'title'},{title:'消费钻石',dataIndex:'units'},...(section.value==='customization'?[{title:'定制单号',dataIndex:'request_id',width:220}]:[]),{title:'履约状态',key:'status'},{title:'时间',key:'time'},...tail];
 return [...head,{title:section.value==='activity'?'回调事件':'异常类型',key:'kind'},{title:'状态',key:'status'},{title:'时间',key:'time'},...tail];});
async function load(background=false){const seq=++generation;if(section.value==='physical'){busy.value=false;return;}busy.value=true;error.value='';if(!background){items.value=[];summary.value={};total.value=0;unlinked.value=0;pendingTopups.value=0;}
try{const r=await http.get<any,any>('/api/v1/billing/manage/transactions/',{params:{environment:environment.value,section:section.value,page:page.value,status:status.value,search:search.value,identity:identity.value||undefined,account:account.value||undefined,start:dates.value?.[0].startOf('day').toISOString(),end:dates.value?.[1].add(1,'day').startOf('day').toISOString()}});if(seq!==generation)return;items.value=r.items;total.value=r.total;summary.value=r.summary;unlinked.value=r.unlinked_events;pendingTopups.value=r.pending_topups;}catch(e:any){if(seq===generation){error.value=e.message||'加载失败';items.value=[];summary.value={};total.value=0;}}finally{if(seq===generation)busy.value=false;}}
function changeSection(){status.value='all';reset();}
function reset(){page.value=1;void load();}function changePage(p:any){page.value=p.current;void load();}
async function show(kind:string,path:string){const seq=++detailGeneration;drawer.value=true;detailKind.value=kind;detail.value=null;detailError.value='';detailBusy.value=true;try{const r=await http.get<any,any>(path);if(seq===detailGeneration)detail.value=r;}catch(e:any){if(seq===detailGeneration)detailError.value=e.message;}finally{if(seq===detailGeneration)detailBusy.value=false;}}
function openPayment(id:string){void show('payment',`/api/v1/billing/manage/transactions/${id}/`);}function openAssets(r:any){void show('assets',`/api/v1/billing/manage/assets/${r.identity_id}/`);}
async function syncAssets(){const id=detail.value.identity_id;syncing.value=true;detailError.value='';try{await http.post(`/api/v1/billing/manage/assets/${id}/`,{}, {timeout:45000});if(detail.value?.identity_id===id)await show('assets',`/api/v1/billing/manage/assets/${id}/`);}catch(e:any){detailError.value=e.message;}finally{syncing.value=false;}}
function filterUser(tab:string){identity.value=detail.value.identity_id;environment.value=detail.value.environment;section.value=tab;drawer.value=false;reset();}
watch(()=>route.query.account,v=>{account.value=String(v||'');reset();});onMounted(()=>{void load();refreshTimer=setInterval(()=>{if(autoRefresh.value&&!drawer.value&&!busy.value&&!document.hidden)void load(true);},30000);});onUnmounted(()=>{if(refreshTimer)clearInterval(refreshTimer);generation++;detailGeneration++;});
</script>
<style scoped>
.transactions{padding:28px;background:white;min-height:75vh}header{display:flex;justify-content:space-between;align-items:center}h1{font-size:26px;margin:0}header p,.muted{color:#78818d}.muted{font-size:12px;word-break:break-all;margin-top:5px}.filters{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}.summary{display:flex;gap:20px;flex-wrap:wrap;padding:16px;background:#f7f9fc;margin-bottom:16px}.summary small{width:100%;color:#78818d}:deep(.ant-alert){margin-bottom:12px}
</style>
