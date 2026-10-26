<template>
 <section class="probe-panel">
  <div class="probe-heading"><strong>当前测试</strong><a-button :loading="busy" :disabled="disabled" @click="$emit('refresh')">刷新测试结果</a-button></div>
  <p>每笔测试 ¥0.01，付款后自动原路退款。请用 iPhone 系统相机扫码，在新版 App 中确认。</p>
  <a-alert v-if="!deviceEnabled" type="info" message="本地仅检查配置；真机联调请使用正式后台 https://diary.dreamwhale.top/print-payments。" show-icon/>
  <div v-if="current" class="current-probe">
   <div class="probe-heading"><strong>{{status(current)}}</strong><a-tag>{{channel}} · ¥0.01 · 版本 {{versionId}}</a-tag></div>
   <dl><dt>测试单号</dt><dd><span :title="current.id">{{shortID(current.id)}}</span> <a-button type="link" size="small" @click="$emit('copy',current.id)">复制</a-button></dd><dt>创建时间</dt><dd>{{date(current.created_at)}}</dd><template v-if="['created','pending','unknown'].includes(current.state)"><dt>扫码有效期</dt><dd>{{expired(current)?'已过期':remaining(current)}} · {{date(current.expires_at)}}</dd></template></dl>
   <div v-if="visibleLink" class="probe">
    <div class="probe-qr"><a-qrcode type="svg" :size="224" color="#000000" bg-color="#ffffff" :value="visibleLink"/></div>
    <div class="probe-instructions"><strong>用 iPhone 系统相机扫码</strong><p>这是打开新版 App 的联调入口，不能用支付宝直接扫码。</p><p>请在 App 内确认支付渠道及 ¥0.01 金额。付款后回到此处刷新结果。</p><a-button @click="$emit('copy',visibleLink)">复制联调链接</a-button></div>
   </div>
   <a-alert v-else-if="expired(current)&&['created','pending','unknown'].includes(current.state)" type="warning" :message="current.state==='created'?'链接已过期，未发起支付，可以重新创建。':'扫码链接已过期，请先查询付款或确认关单；结果未确认前不能创建新单。'" show-icon/>
   <a-alert v-if="current.last_error" type="error" :message="current.last_error" show-icon/>
   <div class="probe-actions">
    <a-button v-if="canResume(current)&&!visibleLink" type="primary" :disabled="busy||disabled" @click="$emit('resume',current.id)">显示二维码</a-button>
    <a-button v-if="current.state==='created'&&!expired(current)" :disabled="busy||disabled" @click="$emit('close',current.id)">作废测试</a-button>
    <a-button v-if="current.state==='created'&&expired(current)" type="primary" :disabled="!canCreate" @click="$emit('restart',current.id)">重新创建测试单</a-button>
    <a-button v-if="['pending','unknown','succeeded'].includes(current.state)" :disabled="busy||disabled" @click="$emit('query',current.id)">{{current.state==='succeeded'?'查询退款进度':'查询支付结果'}}</a-button>
    <a-popconfirm v-if="['pending','unknown'].includes(current.state)" title="先查询支付结果再关单，已付款会原路退款。结果不确定时不会创建新单。" @confirm="$emit('close',current.id)"><a-button :disabled="busy||disabled">取消并确认关单</a-button></a-popconfirm>
   </div>
  </div>
  <a-button v-if="!current||terminal(current)" type="primary" :disabled="!canCreate" :loading="busy" @click="$emit('create')">{{current?'创建新的测试单':'创建 ¥0.01 测试单'}}</a-button>
  <a-collapse v-if="history.length" class="probe-history"><a-collapse-panel key="history" :header="`历史测试（最近 ${history.length} 笔）`"><a-list :data-source="history" size="small"><template #renderItem="{item}"><a-list-item><div><strong>{{status(item)}}</strong><p>{{date(item.created_at)}} · <span :title="item.id">{{shortID(item.id)}}</span><a-button type="link" size="small" @click="$emit('copy',item.id)">复制单号</a-button></p></div></a-list-item></template></a-list></a-collapse-panel></a-collapse>
 </section>
</template>
<script setup lang="ts">
import {computed,onMounted,onBeforeUnmount,ref} from 'vue';
export interface Probe {id:string;state:string;created_at:string;expires_at:string;last_error:string;can_resume:boolean;expired:boolean;refund_state?:string;close_kind?:string}
const props=defineProps<{tests:Probe[];active?:Probe|null;versionId:number;channel:string;link:string;linkProbeId:string;busy:boolean;disabled:boolean;deviceEnabled:boolean;checked:boolean}>();
defineEmits<{create:[];refresh:[];resume:[id:string];close:[id:string];query:[id:string];restart:[id:string];copy:[value:string]}>();
const now=ref(Date.now());let timer:ReturnType<typeof setInterval>|undefined;
onMounted(()=>{timer=setInterval(()=>{now.value=Date.now()},1000)});onBeforeUnmount(()=>{if(timer)clearInterval(timer)});
const terminal=(p:Probe)=>['closed','refunded','expired','discarded'].includes(p.state);
const current=computed(()=>props.active||props.tests.find(p=>!terminal(p))||props.tests[0]);
const history=computed(()=>props.tests.filter(p=>p.id!==current.value?.id));
const expired=(p:Probe)=>p.expired||Date.parse(p.expires_at)<=now.value;
const canResume=(p:Probe)=>['created','pending','unknown'].includes(p.state)&&p.can_resume&&!expired(p);
const visibleLink=computed(()=>current.value&&props.linkProbeId===current.value.id&&canResume(current.value)?props.link:'');
const canCreate=computed(()=>!props.busy&&!props.disabled&&props.deviceEnabled&&props.checked);
const date=(s:string)=>new Date(s).toLocaleString('zh-CN',{hour12:false});
const shortID=(id:string)=>id.length>16?id.slice(0,8)+'…'+id.slice(-6):id;
function remaining(p:Probe){const seconds=Math.max(0,Math.ceil((Date.parse(p.expires_at)-now.value)/1000));return `${Math.floor(seconds/60)} 分 ${String(seconds%60).padStart(2,'0')} 秒`}
function status(p:Probe){if(p.state==='closed'&&p.close_kind==='expired_absent')return '签名已到期 · 未发生交易';if(p.state==='created')return expired(p)?'扫码已过期 · 未发起支付':'待扫码 · 未发起支付';if(p.state==='succeeded')return ['exception','blocked'].includes(p.refund_state||'')?'已付款 · 退款待处理':'已付款 · 等待退款确认';return ({pending:'支付参数已生成 · 等待付款结果',unknown:'支付结果待确认',refunded:'付款与原路退款已完成',closed:'取消与关单已确认',expired:'链接已过期 · 未发起支付',discarded:'已作废 · 未发起支付'} as Record<string,string>)[p.state]||p.state}
</script>
<style scoped>
.probe-panel{display:flex;flex-direction:column;gap:16px;min-width:0}.probe-heading{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}.current-probe{padding:18px;background:#fafcff;border:1px solid #e3e9f0;border-radius:12px;display:flex;flex-direction:column;gap:16px;min-width:0}p{margin:0;color:#5d6878;line-height:1.65}dl{display:grid;grid-template-columns:90px minmax(0,1fr);gap:8px;margin:0;align-items:center}dt{color:#64748b}dd{margin:0;overflow-wrap:anywhere}.probe{display:grid;grid-template-columns:224px minmax(0,1fr);gap:20px;align-items:center;container-type:normal}.probe-qr{width:224px;height:224px;min-width:224px;flex-shrink:0;background:#fff}.probe-qr :deep(.ant-qrcode){flex-shrink:0}.probe-instructions{min-width:0;display:flex;flex-direction:column;align-items:flex-start;gap:12px;overflow-wrap:anywhere}.probe-actions{display:flex;flex-wrap:wrap;gap:10px}.probe-history p{font-size:12px}section{container-type:inline-size}@container (max-width:540px){.probe{grid-template-columns:minmax(0,1fr)}.probe-qr{justify-self:center}}@media(max-width:600px){.probe{grid-template-columns:minmax(0,1fr)}.probe-qr{justify-self:center}}
</style>
