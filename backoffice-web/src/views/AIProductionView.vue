<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useAuthStore } from '../stores/auth';
import { useRoute, useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import http from '../api/http';
interface Policy { id: number; name: string; short_limit: number; weekly_limit: number; hold_hours: number; enabled: boolean; effective_at: string }
interface Task { id: string; account: number; state: string; expires_at: string }
interface Window { kind: string; limit: number; available: number; used: number; reserved: number; reset_at: string|null; starts_at: string|null; status: string; policy_version: number }
interface Ledger { id: number; task_id: string; event: string; reason: string; created_at: string; actor: number }
interface Data { service_control: {accepting:boolean;version:number;reason:string}; current_policy: Policy|null; policies: Policy[]; tasks: Task[]; account_quota: {windows: Window[]}|null; pagination: {total: number; page: number; page_size: number}; ledger: Ledger[] }
interface UserQuota { id:number; username:string; windows:Window[]; can_start:boolean }
const users = ref<UserQuota[]>([]);
const userPage = ref(1);
const userTotal = ref(0);
const userSearch = ref('');
const usersLoading = ref(false);
const usersError = ref('');
let userSequence = 0;
async function loadUsers() {
  const stamp = ++userSequence;
  usersLoading.value = true; usersError.value = '';
  try {
    const result = await http.get<unknown,{items:UserQuota[];pagination:{total:number}}>('/api/admin/v1/ai-production/users/', {params:{page:userPage.value,page_size:25,q:userSearch.value}});
    if(stamp===userSequence) { users.value=result.items;userTotal.value=result.pagination.total; }
  } catch(e) {
    if(stamp===userSequence) usersError.value=e instanceof Error ? e.message : '用户额度读取失败';
  } finally { if(stamp===userSequence) usersLoading.value=false; }
}
const userColumns = [{title:'账户',key:'user'}, {title:'5 小时额度',key:'short'}, {title:'7 天额度',key:'weekly'}, {title:'状态',key:'status'}, {title:'操作',key:'actions'}];
function selectUser(user:UserQuota) {
  account.value=String(user.id);void load();
}
const resetUser = ref<{id:number;username:string}|null>(null);
const resetScope = ref('both');
const resetReason = ref('');
const resetKey = ref('');
const resetBusy = ref(false);
function openReset(user:UserQuota) {
  resetUser.value={id:user.id,username:user.username};
  resetScope.value='both';resetReason.value='';resetKey.value=crypto.randomUUID();
}
async function resetQuota() {
  if(!resetUser.value || !resetReason.value.trim() || resetBusy.value) return;
  resetBusy.value=true;
  try {
    await http.post('/api/admin/v1/ai-production/users/'+resetUser.value.id+'/reset/', {
      request_key:resetKey.value,scope:resetScope.value,reason:resetReason.value.trim()
    });
    resetUser.value=null;
    message.success('额度已重置，下次新制作时开始计时');
    await loadUsers();await load();
  } catch(e) { message.error(e instanceof Error ? e.message : '重置失败，请重试'); }
  finally { resetBusy.value=false; }
}
const data = ref<Data|null>(null);
const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const can = (action:string) => auth.hasPermission('button:ai:production:'+action);
const tab = ref(String(route.query.tab || 'policies'));
const controlOpen = ref(false);
const controlReason = ref('');
const controlBusy = ref(false);
const account = ref(String(route.query.account || ''));
const state = ref<string>();
const taskID = ref(String(route.query.task_id || ''));
const page = ref(1);
const error = ref('');
const loading = ref(false);
const busy = ref(false);
const editing = ref(false);
const preview = ref(false);
const target = ref<Task|null>(null);
const reason = ref('');
const detail = ref<Task|null>(null);
const form = ref({publish_key:crypto.randomUUID(),name: '', short_limit: 3, weekly_limit: 10, hold_hours: 24, enabled: true, reason: ''});
const current = computed(() => data.value?.current_policy);
const states: Record<string,string> = {reserved:'制作中',paused:'已暂停',completed:'已完成',cancelled:'已结束',expired:'预占已到期'};
const events: Record<string,string> = {reserve:'占用次数',settle:'完成扣次',release:'释放占用',refund:'退回次数'};
const time = (value?: string|null) => value ? new Date(value).toLocaleString() : '下次制作时开始计时';
let sequence = 0;
async function load() {
  void router.replace({query:{tab:tab.value,account:account.value || undefined,task_id:taskID.value || undefined}});
  const stamp = ++sequence;
  loading.value = true;
  error.value = '';
  try {
    const result = await http.get<unknown,Data>('/api/admin/v1/ai-production/', {
      params: {account: account.value || undefined, state: state.value, task_id: taskID.value || undefined, page: page.value, page_size: 25}
    });
    if(stamp === sequence) data.value = result;
  } catch(e) { if(stamp === sequence) error.value = e instanceof Error ? e.message : '读取失败，请重试'; }
  finally { if(stamp === sequence) loading.value = false; }
}
function create() {
  form.value = {publish_key:crypto.randomUUID(),name:'',short_limit:current.value?.short_limit ?? 3,weekly_limit:current.value?.weekly_limit ?? 10,hold_hours:current.value?.hold_hours ?? 24,enabled:true,reason:''};
  editing.value = true;
}
async function publish() {
  if(busy.value) return;
  busy.value = true;
  try {
    await http.post('/api/admin/v1/ai-production/', form.value);
    editing.value = false; preview.value = false;
    message.success('策略已发布，新周期采用新规则');
    await load();
  } catch(e) { message.error(e instanceof Error ? e.message : '发布失败，请重试'); }
  finally { busy.value = false; }
}
async function operate() {
  if(!target.value || !reason.value.trim() || busy.value) return;
  busy.value = true;
  try {
    await http.post('/api/admin/v1/ai-production/'+target.value.id+(target.value.state === 'completed' ? '/refund/' : '/release/'), {reason:reason.value});
    target.value = null; reason.value = '';
    message.success('处理完成'); await load();
  } catch(e) { message.error(e instanceof Error ? e.message : '操作失败，请重试'); }
  finally { busy.value = false; }
}
const policyColumns = [{title:'版本',dataIndex:'id'},{title:'策略',dataIndex:'name'},{title:'5 小时次数',dataIndex:'short_limit'},{title:'7 天次数',dataIndex:'weekly_limit'},{title:'策略生效时间',key:'effective_at'}];
const taskColumns = [{title:'任务编号',key:'id'},{title:'账户',dataIndex:'account'},{title:'状态',key:'state'},{title:'预占到期',key:'expires_at'},{title:'操作',key:'actions'}];
async function control() {
  if(!data.value || !controlReason.value.trim()) return;
  controlBusy.value = true;
  try {
    await http.post('/api/admin/v1/ai-production/control/', {
      accepting:!data.value.service_control.accepting,version:data.value.service_control.version,reason:controlReason.value
    });
    controlOpen.value=false;controlReason.value='';message.success('服务状态已更新');await load();
  } catch(e) { message.error(e instanceof Error ? e.message : '操作失败'); }
  finally { controlBusy.value=false; }
}
watch(tab, value => {
  if(value==='users') void loadUsers();
  else void load();
});
onMounted(() => { void load(); if(tab.value==='users') void loadUsers(); });
</script>
<template>
  <div class="production">
    <header><div><h1>AI 制作额度</h1><p>按每位用户首次制作时间计算周期</p></div><a-space><a-button :loading="loading" @click="load">刷新</a-button><a-button v-if="can('publish')" type="primary" @click="create">新建策略</a-button></a-space></header>
    <a-alert v-if="error" type="error" :message="error" show-icon class="notice"/>
    <div class="summary">
      <a-card><a-statistic title="5 小时额度" :value="current?.short_limit ?? '—'" suffix="次"/><p>用户首次制作起，5 小时后恢复</p></a-card>
      <a-card><a-statistic title="7 天额度" :value="current?.weekly_limit ?? '—'" suffix="次"/><p>用户首次制作起，168 小时后恢复</p></a-card>
      <a-card><span class="muted">当前策略</span><h3>{{ current?.name ?? '尚未配置' }}</h3><a-tag :color="current?.enabled && data?.service_control.accepting ? 'green':'default'">{{ current ? (current.enabled && data?.service_control.accepting ? '接受新制作':'暂停新制作') : '等待发布' }}</a-tag><a-button v-if="can('control') && data" type="link" @click="controlOpen=true">{{ data.service_control.accepting ? '暂停新制作':'恢复新制作' }}</a-button></a-card>
    </div>
    <a-card>
      <a-tabs v-model:active-key="tab">
        <a-tab-pane key="policies" tab="策略配置">
          <a-alert type="info" show-icon message="策略生效时间决定新周期使用哪套规则。每位用户的恢复时间由首次制作时间决定。" class="notice"/>
          <a-table :columns="policyColumns" :data-source="data?.policies ?? []" row-key="id" :loading="loading" :pagination="{pageSize:10}" :scroll="{x:650}" :locale="{emptyText:'暂无策略，请新建并发布'}">
            <template #bodyCell="{column,record}"><template v-if="column.key === 'effective_at'">{{ time(record.effective_at) }}</template></template>
          </a-table>
        </a-tab-pane>
        <a-tab-pane key="users" tab="用户额度">
          <a-form layout="inline" class="filters" @finish="userPage=1;loadUsers()">
            <a-form-item label="搜索用户"><a-input v-model:value="userSearch" placeholder="用户名或账户编号" allow-clear/></a-form-item>
            <a-button html-type="submit" :loading="usersLoading">搜索</a-button>
          </a-form>
          <a-alert v-if="usersError" type="error" :message="usersError" show-icon class="notice"/>
          <a-table :columns="userColumns" :data-source="users" row-key="id" :loading="usersLoading" :scroll="{x:650}"
            :locale="{emptyText:usersError ? '加载失败，请重试搜索' : '暂无使用过制作额度的用户'}"
            :pagination="{current:userPage,pageSize:25,total:userTotal,showSizeChanger:false}"
            @change="(p:any)=>{userPage=p.current;loadUsers()}">
            <template #bodyCell="{column,record}">
              <a-button v-if="column.key==='user'" type="link" @click="selectUser(record)">{{record.username}} · {{record.id}}</a-button>
              <template v-else-if="column.key==='short' || column.key==='weekly'">
                <div v-for="w in record.windows.filter((w:Window)=>w.kind===column.key)" :key="w.kind">
                  <strong>可用 {{w.available}} / {{w.limit}} 次</strong>
                  <div class="muted">已用 {{w.used}} · 占用 {{w.reserved}}</div>
                  <div class="muted">{{w.reset_at ? '恢复 '+time(w.reset_at) : '下次制作时开始新周期'}}</div>
                </div>
                <span v-if="!record.windows.length" class="muted">等待配置策略</span>
              </template>
              <a-button v-else-if="column.key==='actions' && can('reset')" type="link" @click="openReset(record)">重置额度</a-button>
              <a-tag v-else-if="column.key==='status'" :color="record.can_start ? 'green':'default'">{{record.can_start ? '可制作':'暂不可开始'}}</a-tag>
            </template>
          </a-table>
          <div v-if="data?.account_quota" class="windows">
            <a-card v-for="w in data.account_quota.windows" :key="w.kind" :title="w.kind === 'short' ? '5 小时额度':'7 天额度'">
              <a-statistic title="可用次数" :value="w.available" :suffix="'/ '+w.limit"/>
              <p>已用 {{ w.used }} 次 · 占用 {{ w.reserved }} 次</p>
              <a-descriptions :column="1" size="small"><a-descriptions-item label="周期开始">{{ time(w.starts_at) }}</a-descriptions-item><a-descriptions-item label="额度恢复">{{ time(w.reset_at) }}</a-descriptions-item><a-descriptions-item label="规则版本">{{ w.policy_version }}</a-descriptions-item></a-descriptions>
            </a-card>
          </div>
        </a-tab-pane>
        <a-tab-pane key="tasks" tab="制作任务">
          <a-form layout="inline" class="filters" @finish="page=1;load()">
            <a-form-item label="账户"><a-input v-model:value="account" placeholder="账户编号" allow-clear/></a-form-item>
            <a-form-item label="任务"><a-input v-model:value="taskID" placeholder="完整任务编号" allow-clear/></a-form-item>
            <a-form-item label="状态"><a-select v-model:value="state" allow-clear placeholder="全部状态" style="width:140px" :options="Object.entries(states).map(([value,label])=>({value,label}))"/></a-form-item>
            <a-button type="primary" html-type="submit">查询</a-button>
          </a-form>
          <a-table :columns="taskColumns" :data-source="data?.tasks ?? []" row-key="id" :loading="loading" :locale="{emptyText:error ? '加载失败，请点击刷新重试' : '暂无制作任务，用户开始制作后会显示在这里'}" :scroll="{x:700}" :pagination="{current:page,pageSize:25,total:data?.pagination.total ?? 0,showSizeChanger:false}" @change="(p:any)=>{page=p.current;load()}">
            <template #bodyCell="{column,record}">
              <a-button v-if="column.key==='id'" type="link" @click="detail=record">{{ record.id.slice(0,8) }}</a-button>
              <a-tag v-else-if="column.key==='state'">{{ states[record.state] ?? record.state }}</a-tag>
              <template v-else-if="column.key==='expires_at'">{{ time(record.expires_at) }}</template>
              <a-button v-else-if="column.key==='actions' && ['completed','reserved','paused'].includes(record.state) && can(record.state==='completed'?'refund':'release')" type="link" @click="target=record;reason=''">{{ record.state==='completed'?'退回次数':'结束并释放' }}</a-button>
            </template>
          </a-table>
        </a-tab-pane>
        <a-tab-pane key="ledger" tab="操作记录">
          <a-table :data-source="data?.ledger ?? []" row-key="id" :loading="loading" :columns="[{title:'事件',key:'event'},{title:'原因',dataIndex:'reason'},{title:'操作者',dataIndex:'actor'},{title:'时间',key:'created_at'}]" :pagination="{pageSize:20}">
            <template #bodyCell="{column,record}"><template v-if="column.key==='event'">{{events[record.event] ?? record.event}}</template><template v-else-if="column.key==='created_at'">{{time(record.created_at)}}</template></template>
          </a-table>
        </a-tab-pane>
      </a-tabs>
    </a-card>
    <a-drawer v-model:open="editing" title="新建制作策略" width="min(600px, 100vw)" :mask-closable="false">
      <a-form layout="vertical" :model="form" @finish="preview=true">
        <a-form-item label="策略名称" name="name" :rules="[{required:true,whitespace:true,message:'填写策略名称'}]"><a-input v-model:value="form.name" :maxlength="100"/></a-form-item>
        <a-form-item label="5 小时制作次数" extra="从每位用户首次成功开始制作计时"><a-input-number v-model:value="form.short_limit" :min="0" :precision="0"/></a-form-item>
        <a-form-item label="7 天制作次数" extra="周期持续 168 小时"><a-input-number v-model:value="form.weekly_limit" :min="0" :precision="0"/></a-form-item>
        <a-divider orientation="left">失败恢复</a-divider>
        <a-form-item label="暂停任务保留小时"><a-input-number v-model:value="form.hold_hours" :min="1" :max="168" :precision="0"/></a-form-item>

        <a-form-item label="变更原因" name="reason" :rules="[{required:true,whitespace:true,message:'填写变更原因'}]"><a-textarea v-model:value="form.reason" :rows="3" :maxlength="500" show-count/></a-form-item>
        <a-button type="primary" html-type="submit">预览变更</a-button>
      </a-form>
    </a-drawer>
    <a-modal :open="!!resetUser" title="重置用户制作额度" ok-text="确认重置" :confirm-loading="resetBusy" :closable="!resetBusy" :mask-closable="false" :cancel-button-props="{disabled:resetBusy}" :ok-button-props="{disabled:!resetReason.trim()}" @cancel="resetUser=null" @ok="resetQuota">
      <p>用户 {{resetUser?.username}} · {{resetUser?.id}}</p>
      <a-form layout="vertical">
        <a-form-item label="重置范围"><a-radio-group v-model:value="resetScope" :disabled="resetBusy"><a-radio value="both">两种额度</a-radio><a-radio value="short">5 小时</a-radio><a-radio value="weekly">7 天</a-radio></a-radio-group></a-form-item>
        <a-alert class="notice" type="warning" show-icon message="结束所选当前周期，下一次新制作重新计时。正在制作的任务仍保留原占用，完成后计入原周期。"/>
        <a-form-item label="操作原因" required><a-textarea v-model:value="resetReason" :disabled="resetBusy" :rows="3" :maxlength="500" placeholder="填写重置原因"/></a-form-item>
      </a-form>
    </a-modal>
    <a-modal v-model:open="controlOpen" title="变更制作服务状态" :confirm-loading="controlBusy" :ok-button-props="{disabled:!controlReason.trim()}" @ok="control">
      <p>{{ data?.service_control.accepting ? '暂停后将拒绝新制作，已占用额度的任务可继续。':'恢复后，按当前策略接受新制作。' }}</p>
      <a-textarea v-model:value="controlReason" placeholder="填写变更原因" :maxlength="500" :rows="3"/>
    </a-modal>
    <a-modal v-model:open="preview" title="确认发布策略" ok-text="确认发布" :confirm-loading="busy" @ok="publish">
      <p>5 小时次数 {{current?.short_limit ?? '未设置'}} → {{form.short_limit}}</p><p>7 天次数 {{current?.weekly_limit ?? '未设置'}} → {{form.weekly_limit}}</p><p>新周期采用此规则。已有周期保留其规则版本。</p><p>变更原因：{{form.reason}}</p><a-alert v-if="!form.enabled" type="warning" message="发布后将暂停接受新制作"/>
    </a-modal>
    <a-modal :open="!!target" :title="target?.state==='completed'?'退回制作次数':'结束任务并释放占用'" :confirm-loading="busy" ok-text="确认处理" :ok-button-props="{disabled:!reason.trim()}" @cancel="target=null" @ok="operate">
      <p>账户 {{target?.account}} · 任务 {{target?.id}}</p><a-alert type="warning" message="操作影响原来的两个窗口。历史窗口退款不会增加当前可用次数。" class="notice"/><a-textarea v-model:value="reason" placeholder="填写处理原因" :rows="3" :maxlength="500"/>
    </a-modal>
    <a-drawer :open="!!detail" title="制作任务详情" width="min(600px, 100vw)" @close="detail=null">
      <a-descriptions v-if="detail" :column="1" bordered><a-descriptions-item label="任务编号"><a-typography-text copyable>{{detail.id}}</a-typography-text></a-descriptions-item><a-descriptions-item label="账户">{{detail.account}}</a-descriptions-item><a-descriptions-item label="状态">{{states[detail.state]}}</a-descriptions-item><a-descriptions-item label="预占到期">{{time(detail.expires_at)}}</a-descriptions-item></a-descriptions>
    </a-drawer>
  </div>
</template>
<style scoped>
.production { padding:24px; }
header { display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:24px; }
h1 { margin:0 0 8px; font-size:24px; } p,.muted { color:#667085; } header p { margin:0; }
.summary { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; margin-bottom:24px; }
.windows { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }
.notice,.filters { margin-bottom:20px; }.filters { gap:12px; }
@media(max-width:800px) { .production { padding:16px; } header { align-items:flex-start; flex-direction:column; } .summary,.windows { grid-template-columns:1fr; } }
</style>
