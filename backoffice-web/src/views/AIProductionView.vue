<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import http from '../api/http';
import { useAuthStore } from '../stores/auth';

const base = '/api/admin/v1/ai-production/';
const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const can = (action: string) => auth.hasPermission('button:ai:production:' + action);
type Rate = {
  category: 'text_ai' | 'image_ai'; mode: 'tokens' | 'images'; input_rate: string;
  cached_input_rate: string; output_rate: string; minimum_charge: string;
  image_rates: Record<string, string>; max_input_tokens: number;
  max_output_tokens: number; max_images: number; usage_timeout_seconds: number;
};
type Policy = {
  id: number; name: string; short_limit_points: string; weekly_limit_points: string;
  effective_at: string; enabled: boolean; rates: Record<string, Rate>;
};
type Control = { accepting: boolean; version: number };
type Window = { kind: string; remaining_points: string; used_points: string; limit_points: string; remaining_ratio: number; reset_at: string | null };
type User = { id: number; username: string; windows: Window[]; pending_usage: boolean };
type Call = {
  call_id: string; account: number; task_id: string; model: string; category: string;
  accounting_state: string; execution_state: string; points: string; source: string;
  created_at: string; version: number; usage?: Record<string, number>;
  ledger?: unknown[]; rate?: Rate; provider_request_id?: string;
};
type Page<T> = { items: T[]; pagination: { total: number } };

const tabs = ['policies', 'rates', 'users', 'calls', 'corrections', 'audit'];
const tab = ref(tabs.includes(String(route.query.tab)) ? String(route.query.tab) : 'policies');
const overview = ref<{ current_policy: Policy | null; policies: Policy[]; service_control: Control }>();
const users = ref<User[]>([]);
const calls = ref<Call[]>([]);
const audit = ref<Record<string, unknown>[]>([]);
const total = ref(0);
const page = ref(1);
const q = ref('');
const account = ref(String(route.query.account || ''));
const category = ref<string>();
const model = ref('');
const taskID = ref('');
const callID = ref('');
const execution = ref<string>();
const accounting = ref<string>();
const since = ref('');
const until = ref('');
const loading = ref(false);
const error = ref('');
let sequence = 0;

async function load() {
  const stamp = ++sequence;
  loading.value = true;
  error.value = '';
  try {
    const params = { page: page.value, page_size: 25 };
    if (tab.value === 'users') {
      const data = await http.get<unknown, Page<User>>(base + 'users/', { params: { ...params, q: q.value } });
      if (stamp === sequence) { users.value = data.items; total.value = data.pagination.total; }
    } else if (tab.value === 'calls' || tab.value === 'corrections') {
      const data = await http.get<unknown, Page<Call>>(base + 'calls/', {
        params: { ...params, account: account.value || undefined, model: model.value || undefined,
          task_id: taskID.value || undefined, call_id: callID.value || undefined,
          category: category.value, accounting_state: tab.value === 'corrections' ? 'estimated' : accounting.value,
          execution_state: execution.value, since: since.value ? new Date(since.value).toISOString() : undefined,
          until: until.value ? new Date(until.value).toISOString() : undefined },
      });
      if (stamp === sequence) { calls.value = data.items; total.value = data.pagination.total; }
    } else if (tab.value === 'audit') {
      const data = await http.get<unknown, Page<Record<string, unknown>>>(base + 'audit/', { params });
      if (stamp === sequence) { audit.value = data.items; total.value = data.pagination.total; }
    } else {
      const data = await http.get<unknown, NonNullable<typeof overview.value>>(base);
      if (stamp === sequence) overview.value = data;
    }
  } catch (failure) {
    if (stamp === sequence) error.value = failure instanceof Error ? failure.message : '读取失败';
  } finally {
    if (stamp === sequence) loading.value = false;
  }
}
function search() { page.value = 1; void load(); }
watch(tab, () => {
  void router.replace({ query: { ...route.query, tab: tab.value, account: account.value || undefined } });
  search();
}, { immediate: true });

const settingsOpen = ref(false);
const draft = ref({ name: '', short_limit_points: '', weekly_limit_points: '', effective_at: '', enabled: true, reason: '' });
const draftRates = ref<(Rate & { model: string; sizes: string })[]>([]);
const publishKey = ref('');
const publishPreview = ref(false);
function addRate() {
  draftRates.value.push({ model: '', category: 'text_ai', mode: 'tokens', input_rate: '0',
    output_rate: '0', cached_input_rate: '0', minimum_charge: '0.01', max_input_tokens: 128000,
    max_output_tokens: 8192, max_images: 1, usage_timeout_seconds: 420, image_rates: {}, sizes: '2K=1' });
}
function editSettings() {
  const current = overview.value?.current_policy;
  draft.value = { name: '', short_limit_points: current?.short_limit_points ?? '',
    weekly_limit_points: current?.weekly_limit_points ?? '', effective_at: '', enabled: true, reason: '' };
  draftRates.value = Object.entries(current?.rates ?? {}).map(([key, rate]) => ({
    ...rate, model: key, sizes: Object.entries(rate.image_rates).map(([size, price]) => size + '=' + price).join(', '),
  }));
  if (!draftRates.value.length) addRate();
  publishKey.value = crypto.randomUUID();
  publishPreview.value = false;
  settingsOpen.value = true;
}
const busy = ref(false);
async function mutate(action: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true;
  try { await action(); }
  catch (failure) { message.error(failure instanceof Error ? failure.message : '操作失败'); }
  finally { busy.value = false; }
}
function rateData(row: (typeof draftRates.value)[number]) {
  const { model: key, sizes, ...rate } = row;
  const image_rates = Object.fromEntries(sizes.split(',').map(pair => pair.trim().split('=').map(v => v.trim()))
    .filter(([name, value]) => name && value));
  return [key.trim(), { ...rate, image_rates: rate.category === 'image_ai' ? image_rates : {} }] as const;
}
async function publish() {
  await mutate(async () => {
    const rates = draftRates.value.map(rateData);
    if (rates.some(([key]) => !key) || new Set(rates.map(([key]) => key)).size !== rates.length) {
      throw new Error('请填写唯一的模型标识');
    }
    await http.post(base, { ...draft.value, publish_key: publishKey.value, rates: Object.fromEntries(rates),
      effective_at: draft.value.effective_at ? new Date(draft.value.effective_at).toISOString() : undefined });
    publishPreview.value = false;
    settingsOpen.value = false;
    message.success('策略已发布');
    await load();
  });
}
const sample = ref({ input: 0, cached: 0, output: 0, images: 1, size: '2K' });
const sampleModel = ref(0);
const trial = ref('');
async function previewPrice() {
  const row = draftRates.value[sampleModel.value];
  if (!row || sample.value.cached > sample.value.input) { trial.value = '请检查模型和使用量'; return; }
  await mutate(async () => {
    const [, rate] = rateData(row);
    const usage = rate.mode === 'images' ? { generated_images: sample.value.images } :
      { input_tokens: sample.value.input, cached_input_tokens: sample.value.cached, output_tokens: sample.value.output };
    const data = await http.post<unknown, { points: string }>(base + 'pricing/preview/', { rate, usage, size: sample.value.size });
    trial.value = data.points + ' 积分';
  });
}
const resetTarget = ref<User>();
const resetScope = ref('both');
const reason = ref('');
const key = ref('');
const controlOpen = ref(false);
function openReset(user: User) {
  resetTarget.value = user; resetScope.value = 'both'; reason.value = ''; key.value = crypto.randomUUID();
}
async function reset() {
  const user = resetTarget.value;
  if (!user) return;
  await mutate(async () => {
    await http.post(base + 'users/' + user.id + '/reset/', { scope: resetScope.value, reason: reason.value, request_key: key.value });
    resetTarget.value = undefined; message.success('额度已重置'); await load();
  });
}
async function control() {
  const state = overview.value?.service_control;
  if (!state) return;
  await mutate(async () => {
    await http.post(base + 'control/', { version: state.version, accepting: !state.accepting, reason: reason.value });
    controlOpen.value = false; message.success('服务状态已更新'); await load();
  });
}

const detail = ref<Call>();
const detailLoading = ref(false);
const adjustOpen = ref(false);
const usageEvidence = ref('');
const adjustedUsage = ref({ input_tokens: 0, cached_input_tokens: 0, output_tokens: 0, generated_images: 0 });
let detailSequence = 0;
async function openCall(id: string) {
  const stamp = ++detailSequence;
  detailLoading.value = true;
  try {
    const data = await http.get<unknown, Call>(base + 'calls/' + id + '/');
    if (stamp === detailSequence) detail.value = data;
  } catch (failure) { if (stamp === detailSequence) message.error(failure instanceof Error ? failure.message : '读取失败'); }
  finally { if (stamp === detailSequence) detailLoading.value = false; }
}
function openAdjust() {
  reason.value = ''; usageEvidence.value = ''; key.value = crypto.randomUUID();
  adjustedUsage.value = { input_tokens: 0, cached_input_tokens: 0, output_tokens: 0, generated_images: 0, ...detail.value?.usage };
  adjustOpen.value = true;
}
async function adjust() {
  const call = detail.value;
  if (!call) return;
  await mutate(async () => {
    const usage = call.rate?.mode === 'images' ? { generated_images: adjustedUsage.value.generated_images } :
      { input_tokens: adjustedUsage.value.input_tokens, cached_input_tokens: adjustedUsage.value.cached_input_tokens,
        output_tokens: adjustedUsage.value.output_tokens };
    await http.post(base + 'calls/' + call.call_id + '/adjustments/', {
      request_key: key.value, version: call.version, usage, evidence: usageEvidence.value, reason: reason.value,
    });
    adjustOpen.value = false;
    await Promise.all([openCall(call.call_id), load()]);
    message.success('用量已更正');
  });
}
const activeRates = computed(() => Object.entries(overview.value?.current_policy?.rates ?? {}).map(([key, item]) => ({ ...item, model: key })));
const userDetail = ref<User>();
const time = (value?: string | null) => value ? new Date(value).toLocaleString() : '首次调用后开始';
const period = (kind: string) => kind === 'short' ? '5 小时' : '7 天';
const categoryName = (value: string) => value === 'text_ai' ? '文本 AI' : '图片 AI';
const states: Record<string, string> = { pending: '待记账', estimated: '估算', actual: '已记账', unknown: '未知',
  completed: '已完成', failed: '失败', cancelled: '已取消', client_reported: '客户端上报', admin_verified: '人工核对' };
const callColumns = [{ title: '调用时间', key: 'created_at' }, { title: '账号', dataIndex: 'account' },
  { title: '模型', dataIndex: 'model' }, { title: '类型', key: 'category' }, { title: '执行', key: 'execution_state' },
  { title: '记账', key: 'accounting_state' }, { title: '积分', dataIndex: 'points' }, { title: '来源', key: 'source' },
  { title: '操作', key: 'actions' }];
const userColumns = [{ title: '账号', dataIndex: 'username' }, { title: '5 小时', key: 'short' },
  { title: '7 天', key: 'weekly' }, { title: '状态', key: 'state' }, { title: '操作', key: 'actions' }];
const auditColumns = [{ title: '时间', key: 'created_at' }, { title: '操作者', dataIndex: 'operator' },
  { title: '动作', dataIndex: 'action' }, { title: '记录', dataIndex: 'resource_id' }];
</script>

<template>
  <main class="production">
    <header>
      <h1>AI 制作用量</h1>
      <a-space>
        <a-button @click="load">刷新</a-button>
        <a-button v-if="overview && can('control')" @click="reason = ''; controlOpen = true">
          {{ overview.service_control.accepting ? '暂停新调用' : '恢复新调用' }}
        </a-button>
      </a-space>
    </header>
    <a-alert v-if="error" type="error" :message="error" show-icon />
    <a-tabs v-model:active-key="tab">
      <a-tab-pane key="policies" tab="额度策略" />
      <a-tab-pane key="rates" tab="模型费率" />
      <a-tab-pane key="users" tab="用户额度" />
      <a-tab-pane key="calls" tab="调用记录" />
      <a-tab-pane key="corrections" tab="用量纠错" />
      <a-tab-pane key="audit" tab="操作审计" />
    </a-tabs>
    <a-card v-if="tab === 'policies' || tab === 'rates'" :loading="loading">
      <template #extra><a-button v-if="can('publish')" type="primary" @click="editSettings">新建策略</a-button></template>
      <template v-if="tab === 'policies'">
        <p>生效策略 {{ overview?.current_policy?.name ?? '尚未配置' }}</p>
        <a-table :data-source="overview?.policies ?? []" row-key="id" :pagination="false"
          :columns="[{title:'版本',dataIndex:'id'},{title:'名称',dataIndex:'name'},
            {title:'5 小时积分',dataIndex:'short_limit_points'},{title:'7 天积分',dataIndex:'weekly_limit_points'},
            {title:'生效时间',key:'time'}]">
          <template #bodyCell="{ column, record }"><span v-if="column.key === 'time'">{{ time(record.effective_at) }}</span></template>
        </a-table>
      </template>
      <a-table v-else :data-source="activeRates" row-key="model" :pagination="false"
        :columns="[{title:'模型',dataIndex:'model'},{title:'类型',key:'category'},{title:'计量',dataIndex:'mode'},
          {title:'输入 / 缓存 / 输出',key:'tokens'},{title:'最低消耗',dataIndex:'minimum_charge'},{title:'图片规格',key:'sizes'}]">
        <template #bodyCell="{ column, record }">
          <span v-if="column.key === 'category'">{{ categoryName(record.category) }}</span>
          <span v-if="column.key === 'tokens'">{{ record.input_rate }} / {{ record.cached_input_rate }} / {{ record.output_rate }}</span>
          <span v-if="column.key === 'sizes'">{{ record.image_rates }}</span>
        </template>
      </a-table>
    </a-card>

    <template v-if="tab === 'users'">
      <a-input-search v-model:value="q" placeholder="账号 ID 或用户名" class="search" @search="search" />
      <a-table :columns="userColumns" :data-source="users" :loading="loading" row-key="id" :pagination="false"
        :locale="{ emptyText: q.trim() ? '未找到有额度消耗记录的账号' : '暂无额度消耗记录' }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'short' || column.key === 'weekly'">
            <div v-for="window in record.windows.filter((w: Window) => w.kind === column.key)" :key="window.kind">
              {{ window.remaining_points }} / {{ window.limit_points }} 积分 · {{ (window.remaining_ratio * 100).toFixed(1) }}%
              <div>{{ time(window.reset_at) }}</div>
            </div>
          </template>
          <span v-if="column.key === 'state'">{{ record.pending_usage ? '用量更新中' : '—' }}</span>
          <a-space v-if="column.key === 'actions'">
            <a-button type="link" @click="userDetail = record">详情</a-button>
            <a-button v-if="can('reset')" type="link" @click="openReset(record)">重置额度</a-button>
          </a-space>
        </template>
      </a-table>
    </template>

    <template v-if="tab === 'calls' || tab === 'corrections'">
      <a-space wrap class="filters">
        <a-input v-model:value="account" placeholder="账号 ID" />
        <a-input v-model:value="model" placeholder="模型标识" />
        <a-input v-model:value="taskID" placeholder="制作任务 ID" />
        <a-input v-model:value="callID" placeholder="调用 ID" />
        <a-select v-model:value="category" allow-clear placeholder="类型" style="width: 120px">
          <a-select-option value="text_ai">文本 AI</a-select-option><a-select-option value="image_ai">图片 AI</a-select-option>
        </a-select>
        <a-select v-if="tab === 'calls'" v-model:value="accounting" allow-clear placeholder="记账状态" style="width: 125px">
          <a-select-option v-for="state in ['pending','actual','estimated']" :key="state" :value="state">{{ states[state] }}</a-select-option>
        </a-select>
        <a-select v-model:value="execution" allow-clear placeholder="执行状态" style="width: 125px">
          <a-select-option v-for="state in ['completed','failed','cancelled','unknown']" :key="state" :value="state">{{ states[state] }}</a-select-option>
        </a-select>
        <label>开始 <input type="datetime-local" v-model="since"></label>
        <label>结束 <input type="datetime-local" v-model="until"></label>
        <a-button @click="search">查询</a-button>
      </a-space>
      <a-table :columns="callColumns" :data-source="calls" :loading="loading" row-key="call_id" :pagination="false">
        <template #bodyCell="{ column, record }">
          <span v-if="column.key === 'created_at'">{{ time(record.created_at) }}</span>
          <span v-if="column.key === 'category'">{{ categoryName(record.category) }}</span>
          <span v-if="column.key && ['execution_state','accounting_state','source'].includes(String(column.key))">{{ states[record[String(column.key)]] ?? '—' }}</span>
          <a-button v-if="column.key === 'actions'" type="link" :loading="detailLoading" @click="openCall(record.call_id)">查看</a-button>
        </template>
      </a-table>
    </template>

    <a-table v-if="tab === 'audit'" :columns="auditColumns" :data-source="audit" :loading="loading" row-key="id" :pagination="false">
      <template #bodyCell="{ column, record }"><span v-if="column.key === 'created_at'">{{ time(String(record.created_at)) }}</span></template>
    </a-table>
    <a-pagination v-if="['users','calls','corrections','audit'].includes(tab)" v-model:current="page" :total="total"
      :page-size="25" :show-size-changer="false" @change="load" />

    <a-drawer :open="settingsOpen" title="新建策略" width="min(780px, 100vw)" @close="settingsOpen = false">
      <a-form layout="vertical">
        <a-form-item label="策略名称"><a-input v-model:value="draft.name" /></a-form-item>
        <a-space wrap>
          <a-form-item label="5 小时积分上限"><a-input v-model:value="draft.short_limit_points" /></a-form-item>
          <a-form-item label="7 天积分上限"><a-input v-model:value="draft.weekly_limit_points" /></a-form-item>
          <a-form-item label="生效时间（可选）"><input v-model="draft.effective_at" type="datetime-local"></a-form-item>
          <a-form-item label="启用"><a-switch v-model:checked="draft.enabled" /></a-form-item>
        </a-space>
        <a-card v-for="(rate, index) in draftRates" :key="index" class="rate" :title="'模型 ' + (index + 1)">
          <template #extra><a-button type="link" danger @click="draftRates.splice(index, 1)">移除</a-button></template>
          <a-form-item label="运行配置模型标识"><a-input v-model:value="rate.model" /></a-form-item>
          <a-space wrap>
            <a-form-item label="分类"><a-select v-model:value="rate.category" style="width: 120px" @change="rate.mode = 'tokens'">
              <a-select-option value="text_ai">文本 AI</a-select-option><a-select-option value="image_ai">图片 AI</a-select-option>
            </a-select></a-form-item>
            <a-form-item label="计量方式"><a-select v-model:value="rate.mode" style="width: 125px">
              <a-select-option value="tokens">Token</a-select-option><a-select-option v-if="rate.category === 'image_ai'" value="images">图片张数</a-select-option>
            </a-select></a-form-item>
            <a-form-item label="最低调用积分"><a-input v-model:value="rate.minimum_charge" /></a-form-item>
          </a-space>
          <a-space v-if="rate.mode === 'tokens'" wrap>
            <a-form-item label="每千输入 token"><a-input v-model:value="rate.input_rate" /></a-form-item>
            <a-form-item label="每千缓存输入 token"><a-input v-model:value="rate.cached_input_rate" /></a-form-item>
            <a-form-item label="每千输出 token"><a-input v-model:value="rate.output_rate" /></a-form-item>
            <a-form-item label="输入预算 token"><a-input-number v-model:value="rate.max_input_tokens" :min="1" /></a-form-item>
            <a-form-item label="输出预算 token"><a-input-number v-model:value="rate.max_output_tokens" :min="1" /></a-form-item>
          </a-space>
          <a-space wrap>
            <a-form-item v-if="rate.category === 'image_ai'" label="尺寸与每张积分（如 2K=1, 4K=2）"><a-input v-model:value="rate.sizes" /></a-form-item>
            <a-form-item v-if="rate.mode === 'images'" label="最大生成张数"><a-input-number v-model:value="rate.max_images" :min="1" /></a-form-item>
            <a-form-item label="用量等待秒数"><a-input-number v-model:value="rate.usage_timeout_seconds" :min="360" /></a-form-item>
          </a-space>
        </a-card>
        <a-button @click="addRate">添加模型</a-button>
        <a-card title="费率试算" class="rate">
          <a-space wrap>
            <a-select v-model:value="sampleModel" style="width: 160px">
              <a-select-option v-for="(rate, i) in draftRates" :key="i" :value="i">{{ rate.model || ('模型 ' + (i + 1)) }}</a-select-option>
            </a-select>
            <template v-if="draftRates[sampleModel]?.mode === 'images'">
              <label>张数 <a-input-number v-model:value="sample.images" :min="0" /></label>
              <label>尺寸 <a-input v-model:value="sample.size" /></label>
            </template>
            <template v-else>
              <label>输入 <a-input-number v-model:value="sample.input" :min="0" /></label>
              <label>缓存 <a-input-number v-model:value="sample.cached" :min="0" /></label>
              <label>输出 <a-input-number v-model:value="sample.output" :min="0" /></label>
            </template>
            <a-button :loading="busy" @click="previewPrice">计算</a-button><span>{{ trial }}</span>
          </a-space>
        </a-card>
        <a-form-item label="发布原因"><a-textarea v-model:value="draft.reason" /></a-form-item>
        <a-button type="primary" :disabled="!draft.name || !draft.reason || !draftRates.length" @click="publishPreview = true">预览发布</a-button>
      </a-form>
    </a-drawer>
    <a-modal v-model:open="publishPreview" title="发布额度策略" :confirm-loading="busy" @ok="publish">
      <p>{{ draft.name }} · 5 小时 {{ draft.short_limit_points }} 积分 · 7 天 {{ draft.weekly_limit_points }} 积分</p>
      <p>模型 {{ draftRates.map(rate => rate.model).join('、') }}</p>
    </a-modal>

    <a-drawer :open="!!userDetail" title="用户额度" @close="userDetail = undefined">
      <template v-if="userDetail">
        <p>{{ userDetail.username }} · {{ userDetail.id }}</p>
        <p v-for="window in userDetail.windows" :key="window.kind">{{ period(window.kind) }} · 已用 {{ window.used_points }} · 剩余 {{ window.remaining_points }} 积分</p>
        <a-button @click="account = String(userDetail.id); userDetail = undefined; tab = 'calls'">查看调用记录</a-button>
      </template>
    </a-drawer>
    <a-modal :open="!!resetTarget" title="重置额度" :confirm-loading="busy" :ok-button-props="{ disabled: !reason.trim() }"
      @cancel="resetTarget = undefined" @ok="reset">
      <p>{{ resetTarget?.username }} · 下次调用开始新周期</p>
      <a-radio-group v-model:value="resetScope" :options="[{label:'5 小时',value:'short'},{label:'7 天',value:'weekly'},{label:'两者',value:'both'}]" />
      <a-textarea v-model:value="reason" placeholder="操作原因" />
    </a-modal>
    <a-modal v-model:open="controlOpen" :title="overview?.service_control.accepting ? '暂停新调用' : '恢复新调用'"
      :confirm-loading="busy" :ok-button-props="{ disabled: !reason.trim() }" @ok="control">
      <a-textarea v-model:value="reason" placeholder="操作原因" />
    </a-modal>

    <a-drawer :open="!!detail" title="调用详情" width="min(640px, 100vw)" @close="detail = undefined">
      <template v-if="detail">
        <p>{{ detail.call_id }} · {{ detail.model }} · {{ detail.points }} 积分</p>
        <p>供应商请求 {{ detail.provider_request_id || '—' }}</p>
        <p>来源 {{ states[detail.source] ?? '—' }} · {{ states[detail.accounting_state] }}</p>
        <a-collapse>
          <a-collapse-panel key="usage" header="实际用量"><pre>{{ detail.usage }}</pre></a-collapse-panel>
          <a-collapse-panel key="rate" header="费率快照"><pre>{{ detail.rate }}</pre></a-collapse-panel>
          <a-collapse-panel key="ledger" header="积分流水"><pre>{{ detail.ledger }}</pre></a-collapse-panel>
        </a-collapse>
        <a-button v-if="can('adjust')" @click="openAdjust">更正用量</a-button>
      </template>
    </a-drawer>
    <a-modal v-model:open="adjustOpen" title="更正用量" :confirm-loading="busy"
      :ok-button-props="{ disabled: !reason.trim() || !usageEvidence.trim() }" @ok="adjust">
      <p>当前 {{ detail?.points }} 积分。更正写入调用原属周期。</p>
      <label v-if="detail?.rate?.mode === 'images'">图片张数 <a-input-number v-model:value="adjustedUsage.generated_images" :min="0" /></label>
      <a-space v-else wrap>
        <label>输入 <a-input-number v-model:value="adjustedUsage.input_tokens" :min="0" /></label>
        <label>缓存 <a-input-number v-model:value="adjustedUsage.cached_input_tokens" :min="0" /></label>
        <label>输出 <a-input-number v-model:value="adjustedUsage.output_tokens" :min="0" /></label>
      </a-space>
      <a-input v-model:value="usageEvidence" placeholder="供应商证据编号" />
      <a-textarea v-model:value="reason" placeholder="更正原因" />
    </a-modal>
  </main>
</template>

<style scoped>
.production { display: grid; gap: 16px; }
header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
h1 { margin: 0; }
.search { max-width: 320px; }
.rate { margin: 12px 0; }
.filters { margin-bottom: 12px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
