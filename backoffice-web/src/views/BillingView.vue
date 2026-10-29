<script setup lang="ts">
import CustomizationPackagesPanel from '../components/billing/CustomizationPackagesPanel.vue';
import BillingOperationsPanel from '../components/billing/BillingOperationsPanel.vue';
import { ref, onMounted, computed, nextTick } from 'vue';
import type { FormInstance } from 'ant-design-vue';
import http from '../api/http';
import { useAuthStore } from '../stores/auth';
const auth = useAuthStore();
type Offer = { id: string; title: string; target_kind: string; revision: number; access_mode: string | null; diamond_price: number | null };
const offers = ref<Offer[]>([]), selected = ref<Offer | null>(null), error = ref(''), busy = ref(false), preview = ref<any>(null);
const draft = ref({ expected_revision: 0, access_mode: 'free', diamond_price: null as number | null, currency_code: null as string | null, pro_entitlement_key: null as string | null, bundled_grants: [], terms_version: 'content-personal-v1', change_reason: '' });
const policyForm = ref<FormInstance>();
const savedSignature = ref<string | null>(null), success = ref(''), staleDraftNotice = ref('');
const reasonRules = [{ required: true, whitespace: true, message: '请填写变更说明，说明本次调整的原因', trigger: ['blur', 'change'] }, { max: 500, message: '变更说明最多 500 字', trigger: ['blur', 'change'] }];
const priceRules = [{ validator: async (_rule: unknown, value: unknown) => {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 1 || value > 1000000) throw new Error('请输入 1 至 1000000 的整数钻石价格');
}, trigger: ['blur', 'change'] }];
function policyBody() { return { ...draft.value, change_reason: draft.value.change_reason.trim(), diamond_price: diamond.value ? draft.value.diamond_price : null, currency_code: diamond.value ? 'DIAMOND' : null, pro_entitlement_key: ['pro_only','pro_or_diamond'].includes(draft.value.access_mode) ? 'member' : null }; }
function signature(value: typeof draft.value) { return JSON.stringify([value.expected_revision,value.access_mode,value.diamond_price,value.currency_code,value.pro_entitlement_key,value.bundled_grants,value.terms_version,value.change_reason]); }
const hasUnsavedChanges = computed(() => savedSignature.value !== signature(policyBody()));
const testPolicyChangesEnabled = ref(false);
const registration = ref({ target_kind: 'template', target_id: '' });
async function register() { await run(async () => { const response = await http.post<Offer, Offer>(base, registration.value); await load(); await edit(response); }); }
const base = '/api/v1/billing/manage/content-offers/';
const diamond = computed(() => ['diamond_only','pro_or_diamond'].includes(draft.value.access_mode));
const canPublish = computed(() => auth.hasPermission('billing.publish_pricing'));
async function run(task: () => Promise<void>) { busy.value = true; error.value = ''; success.value = ''; try { await task(); } catch(e) { error.value = e instanceof Error ? e.message : String(e); } finally { busy.value = false; } }
async function load() { const response = await http.get<{items: Offer[];test_policy_changes_enabled?:boolean}, {items: Offer[];test_policy_changes_enabled?:boolean}>(base); offers.value = response.items; testPolicyChangesEnabled.value = response.test_policy_changes_enabled === true; }
async function edit(offer: Offer) { await run(async () => { selected.value = offer; preview.value = null; savedSignature.value = null; staleDraftNotice.value = ''; const response = await http.get<{draft: typeof draft.value | null;offer?:Offer;stale_draft?:boolean}, {draft: typeof draft.value | null;offer?:Offer;stale_draft?:boolean}>(`${base}${offer.id}/draft/`); const current = response.offer ?? offer; selected.value = current; if(response.stale_draft) staleDraftNotice.value = '旧草稿已过期，已加载当前已发布策略，请重新填写变更说明并保存。'; draft.value = response.draft ?? { expected_revision: current.revision, access_mode: current.access_mode ?? 'free', diamond_price: current.diamond_price, currency_code: current.diamond_price ? 'DIAMOND' : null, pro_entitlement_key: ['pro_only','pro_or_diamond'].includes(current.access_mode ?? '') ? 'member' : null, bundled_grants: [], terms_version: 'content-personal-v1', change_reason: '' }; savedSignature.value = response.draft ? signature(policyBody()) : null; await nextTick(); policyForm.value?.clearValidate(); }); }
async function save() {
  if(!selected.value || busy.value) return;
  error.value = ''; success.value = '';
  try { await policyForm.value?.validate(); } catch { return; }
  await run(async () => {
    const response = await http.patch<{draft: typeof draft.value}, {draft: typeof draft.value}>(`${base}${selected.value!.id}/draft/`,policyBody());
    draft.value = response.draft;
    savedSignature.value = signature(policyBody());
    staleDraftNotice.value = '';
    preview.value = null;
    success.value = '草稿已保存，在线策略尚未变更。可以继续校验与查看影响。';
  });
}
async function inspect() {
  if(!selected.value || busy.value || hasUnsavedChanges.value) return;
  await run(async () => { preview.value=await http.post<unknown, Record<string, any>>(`${base}${selected.value!.id}/publish-preview/`); });
}
async function publish() { if(!selected.value || !preview.value?.deliverable)return; await run(async () => { await http.post(`${base}${selected.value!.id}/publish/`,{expected_draft_hash:preview.value.draft_hash}); selected.value=null; preview.value=null; await load(); }); }
onMounted(() => run(load));
</script>
<template>
  <section class="billing-page">
    <h1>收费与权限</h1><p>先保存草稿并查看影响，再发布新的收费策略。已永久解锁的内容保留原许可。</p>
    <a-alert v-if="testPolicyChangesEnabled" type="info" message="当前为本地测试配置：钻石兑换已开放，允许将已有免费内容改为收费进行测试。" show-icon style="margin-bottom:16px" />
    <a-alert v-if="error && !selected" type="error" :message="error" show-icon />
    <a-space style="margin:16px 0" v-if="auth.hasPermission('billing.change_pricing_draft')">
      <a-select v-model:value="registration.target_kind" style="width:130px" :options="[{value:'template',label:'手帐模板'},{value:'sticker_library',label:'贴纸包'},{value:'font',label:'字体'}]" />
      <a-input v-model:value="registration.target_id" placeholder="内容 UUID" style="width:340px" />
      <a-button :loading="busy" :disabled="!registration.target_id" @click="register">添加收费策略草稿</a-button>
    </a-space>
    <a-table :data-source="offers" row-key="id" :loading="busy" :columns="[{title:'内容',dataIndex:'title'},{title:'类型',dataIndex:'target_kind'},{title:'访问模式',dataIndex:'access_mode'},{title:'钻石价',dataIndex:'diamond_price'},{title:'版本',dataIndex:'revision'},{title:'操作',key:'action'}]">
      <template #bodyCell="{column,record}"><a-button v-if="column.key==='action'" @click="edit(record)">编辑策略</a-button></template>
    </a-table>
    <a-collapse style="margin:24px 0"><a-collapse-panel key="packages" header="数字定制套餐"><CustomizationPackagesPanel /></a-collapse-panel><a-collapse-panel key="operations" header="钻石交易与异常核查"><BillingOperationsPanel /></a-collapse-panel></a-collapse>
    <a-drawer :open="!!selected" title="收费与权限" :width="520" @close="selected=null">
      <a-alert v-if="staleDraftNotice" type="info" :message="staleDraftNotice" show-icon style="margin-bottom:16px" />
      <a-alert v-if="error" type="error" :message="error" show-icon style="margin-bottom:16px" />
      <a-alert v-if="success && !hasUnsavedChanges" type="success" :message="success" show-icon style="margin-bottom:16px" />
      <a-form ref="policyForm" :model="draft" :disabled="busy" layout="vertical">
        <a-form-item label="内容">{{ selected?.title }}</a-form-item>
        <a-form-item label="访问模式"><a-select v-model:value="draft.access_mode" :options="[{value:'free',label:'免费'},{value:'pro_only',label:'Pro 专享'},{value:'diamond_only',label:'钻石永久解锁'},{value:'pro_or_diamond',label:'Pro 或钻石永久解锁'}]" /></a-form-item>
        <a-form-item v-if="diamond" label="钻石售价" name="diamond_price" :rules="priceRules"><a-input-number v-model:value="draft.diamond_price" :min="1" :max="1000000" :precision="0" /></a-form-item>
        <a-form-item label="变更说明" name="change_reason" :rules="reasonRules"><a-textarea v-model:value="draft.change_reason" :maxlength="500" show-count placeholder="必填，例如：新增旅行主题包，设置首次钻石售价" /></a-form-item>
        <a-space><a-button :loading="busy" @click="save">保存草稿</a-button><a-button :loading="busy" :disabled="hasUnsavedChanges" @click="inspect">校验与查看影响</a-button></a-space>
        <p v-if="hasUnsavedChanges" style="color:#666;margin-top:12px">请先保存当前草稿，再校验与查看影响。</p>
        <div v-if="preview && !hasUnsavedChanges" class="impact"><p>即将发布：{{ preview.draft.access_mode }}；钻石价格：{{ preview.draft.diamond_price ?? '无' }}</p><p>已拥有用户：{{ preview.owned_users }}；待处理订单：{{ preview.pending_orders }}</p><p>内容交付校验：{{ preview.deliverable ? '通过' : '未通过' }}</p><a-popconfirm title="确认发布已保存的收费策略草稿？" @confirm="publish"><a-button type="primary" :disabled="!canPublish || !preview.deliverable" :loading="busy">发布已保存草稿</a-button></a-popconfirm></div>
      </a-form>
    </a-drawer>
  </section>
</template>
<style scoped>.billing-page{padding:24px}.impact{margin-top:24px}</style>
