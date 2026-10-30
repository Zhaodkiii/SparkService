<template>
 <section v-if="auth.user?.is_superuser" class="sales-summary" aria-label="当前环境销售状态">
  <div class="summary-main"><strong>销售状态</strong><a-tag :color="saved?.environment==='production'?'red':'blue'">{{environmentLabel}}</a-tag><span v-if="saved" class="status"><i :class="{enabled:saved.diamond_redemption_enabled}"/>钻石兑换 {{saved.diamond_redemption_enabled?'已开放':'已关闭'}}</span><span v-if="saved" class="status"><i :class="{enabled:saved.membership_sales_enabled}"/>会员销售 {{saved.membership_sales_enabled?'已开放':'已关闭'}}</span><span v-if="!saved" class="muted">{{error?'状态加载失败':'正在读取状态…'}}</span></div>
  <a-button :loading="loading" @click="openSettings">{{error?'重试 / 设置':'管理销售设置'}}</a-button>
  <a-modal :open="open" title="当前环境销售设置" :width="600" :confirm-loading="busy" :ok-button-props="{disabled:!changed||!reason.trim()||loading}" ok-text="检查并保存" cancel-text="关闭" :mask-closable="!changed&&!busy" :closable="!busy" @cancel="close" @ok="confirm">
   <a-alert v-if="error" type="error" :message="error" show-icon><template #action><a-button :loading="loading" @click="load">重试</a-button></template></a-alert>
   <template v-if="saved"><a-alert type="info" show-icon :message="`${environmentLabel} · 仅影响当前环境`" :description="saved.environment==='production'?'修改将在当前生产环境立即生效。':'此处修改不会更改生产环境的销售设置。'"/>
    <div class="setting"><div><strong>钻石兑换</strong><p>允许用户用钻石解锁内容，并允许首次同步钻石收费策略。充值另行配置。</p></div><a-switch v-model:checked="diamond" :disabled="busy" checked-children="开放" un-checked-children="关闭" aria-label="钻石兑换"/></div>
    <div class="setting"><div><strong>会员销售</strong><p>控制会员销售及首次同步 Pro 策略；已有购买权益按权益记录处理。</p></div><a-switch v-model:checked="membership" :disabled="busy" checked-children="开放" un-checked-children="关闭" aria-label="会员销售"/></div>
    <a-alert v-if="changed" type="warning" show-icon message="设置已修改，保存后才会生效"/>
    <a-form layout="vertical"><a-form-item label="修改原因" required><a-textarea v-model:value="reason" :disabled="busy" :rows="2" :maxlength="500" show-count placeholder="说明本次开放或关闭的原因"/></a-form-item></a-form>
    <p v-if="saved.updated_at" class="muted">最近修改：{{saved.updated_by}} · {{formatDate(saved.updated_at)}}</p>
    <a-button :disabled="busy||changed" :loading="loading" @click="load">刷新状态</a-button>
   </template>
  </a-modal>
 </section>
</template>
<script setup lang="ts">
import {ref,computed,onMounted} from 'vue';
import {Modal,message} from 'ant-design-vue';
import http from '../api/http';
import {useAuthStore} from '../stores/auth';
import {formatDate} from '../features/billing/policy';
const emit=defineEmits<{changed:[]}>();
const auth=useAuthStore(),saved=ref<any>(),diamond=ref(false),membership=ref(false),reason=ref(''),error=ref(''),busy=ref(false),loading=ref(false),open=ref(false);
const url='/api/v1/billing/manage/sales-settings/';
const environmentLabel=computed(()=>({production:'生产环境','local-authoring':'本地内容编制环境',sandbox:'沙盒环境'}[String(saved.value?.environment)]||saved.value?.environment||'当前环境'));
const changed=computed(()=>!!saved.value&&(diamond.value!==saved.value.diamond_redemption_enabled||membership.value!==saved.value.membership_sales_enabled));
function apply(data:any){saved.value=data;diamond.value=data.diamond_redemption_enabled;membership.value=data.membership_sales_enabled;reason.value='';}
async function load(){if(loading.value)return;loading.value=true;error.value='';try{apply(await http.get(url));}catch(e:any){error.value=e?.response?.data?.message||e.message;}finally{loading.value=false;}}
function openSettings(){open.value=true;if(saved.value)apply(saved.value);else void load();}
function close(){if(busy.value)return;if(changed.value||reason.value.trim()){Modal.confirm({title:'放弃尚未保存的销售设置？',okText:'放弃修改',cancelText:'继续编辑',onOk:()=>{apply(saved.value);open.value=false;}});}else open.value=false;}
function confirm(){if(!changed.value||!reason.value.trim()||busy.value)return;Modal.confirm({title:`确认修改${environmentLabel.value}的销售设置`,content:`钻石兑换：${saved.value.diamond_redemption_enabled?'开放':'关闭'} → ${diamond.value?'开放':'关闭'}；会员销售：${saved.value.membership_sales_enabled?'开放':'关闭'} → ${membership.value?'开放':'关闭'}。保存后立即生效，并记录操作审计。`,okText:'确认保存',cancelText:'继续检查',onOk:save});}
async function save(){busy.value=true;error.value='';try{apply(await http.patch(url,{expected_revision:saved.value.revision,diamond_redemption_enabled:diamond.value,membership_sales_enabled:membership.value,reason:reason.value.trim()}));open.value=false;message.success('销售设置已生效');emit('changed');}catch(e:any){error.value=e?.response?.data?.message||e.message;}finally{busy.value=false;}}
onMounted(()=>{if(auth.user?.is_superuser)void load();});
</script>
<style scoped>
.sales-summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;background:#f8fafc;border:1px solid #e5eaf2;border-radius:8px;margin-top:20px}.summary-main{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.summary-main .ant-tag{margin:0}.status{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:#475569}.status i{width:7px;height:7px;border-radius:50%;background:#94a3b8}.status i.enabled{background:#16a34a}.muted{font-size:12px;color:#64748b}.setting{display:flex;justify-content:space-between;align-items:center;gap:24px;padding:20px 0;border-bottom:1px solid #e5eaf2}.setting p{margin:6px 0 0;color:#64748b;font-size:13px}.setting .ant-switch{flex-shrink:0}:deep(.ant-alert){margin-bottom:16px}.ant-form{margin-top:20px}@media(max-width:600px){.sales-summary{align-items:flex-start;flex-direction:column}.summary-main{gap:8px}.sales-summary>.ant-btn{align-self:flex-end}}
</style>
