<template>
  <a-space wrap style="margin-bottom: 16px">
    <a-input-search v-model:value="query.q" placeholder="显示名称 / 账号标识 / 邮箱" enter-button @search="onSearch" style="width: 320px" />
    <a-select v-model:value="query.is_active" style="width: 140px" @change="onSearch">
      <a-select-option value="">全部状态</a-select-option>
      <a-select-option value="true">启用</a-select-option>
      <a-select-option value="false">禁用</a-select-option>
    </a-select>
    <a-input
      v-model:value="query.bundle_id"
      placeholder="bundle_id"
      style="width: 200px"
      allow-clear
      @pressEnter="onSearch"
    />
    <a-range-picker
      v-model:value="joinedRange"
      show-time
      format="YYYY-MM-DD HH:mm:ss"
      :placeholder="['注册开始', '注册结束']"
      @change="onJoinedRangeChange"
    />
    <a-range-picker
      v-model:value="lastUsedRange"
      show-time
      format="YYYY-MM-DD HH:mm:ss"
      :placeholder="['最近使用开始', '最近使用结束']"
      @change="onLastUsedRangeChange"
    />
    <a-button type="primary" @click="onSearch">查询</a-button>
    <a-button @click="onReset">重置</a-button>
  </a-space>

  <a-table
    :data-source="rows"
    :pagination="false"
    row-key="id"
    :loading="loading"
    :scroll="{ x: 1500 }"
    @change="handleTableChange"
  >
    <a-table-column
      title="ID"
      data-index="id"
      key="id"
      :width="90"
      :sorter="true"
      :sort-order="getColumnSortOrder('id')"
    />
    <a-table-column title="显示名称" data-index="display_name" :width="140">
      <template #default="{ record }">
        {{ record.display_name || '-' }}
      </template>
    </a-table-column>
    <a-table-column title="账号标识" data-index="username" :width="200" ellipsis />
    <a-table-column title="邮箱" data-index="email" :width="220">
      <template #default="{ record }">
        {{ record.email || '-' }}
      </template>
    </a-table-column>
    <a-table-column title="状态" key="status" :width="90">
      <template #default="{ record }">
        <a-tag :color="record.is_active ? 'green' : 'red'">{{ record.is_active ? '启用' : '禁用' }}</a-tag>
      </template>
    </a-table-column>
    <a-table-column title="是否 Pro" key="is_pro" :width="100">
      <template #default="{ record }">
        <a-tag :color="record.is_pro ? 'green' : 'default'">{{ record.is_pro ? 'Pro' : '非 Pro' }}</a-tag>
      </template>
    </a-table-column>
    <a-table-column
      title="注册时间"
      key="date_joined"
      data-index="date_joined"
      :width="180"
      :sorter="true"
      :sort-order="getColumnSortOrder('date_joined')"
    >
      <template #default="{ record }">
        {{ formatDateTime(record.date_joined) }}
      </template>
    </a-table-column>
    <a-table-column
      title="最近使用时间"
      key="last_used_at"
      data-index="last_used_at"
      :width="180"
      :sorter="true"
      :sort-order="getColumnSortOrder('last_used_at')"
    >
      <template #default="{ record }">
        {{ formatDateTime(record.last_used_at) }}
      </template>
    </a-table-column>
    <a-table-column title="操作" key="actions" :width="actionsColWidth" fixed="right">
      <template #default="{ record }">
        <TableHoverActions>
          <a-button size="small" @click="openUserDetail(record)">详细</a-button>
          <a-button size="small" @click="openMedicalDetail(record)">医疗详情</a-button>
          <a-button v-if="canUpdate" size="small" @click="onStatusAction(record)">
            {{ record.is_active ? '禁用' : '启用' }}
          </a-button>
        </TableHoverActions>
      </template>
    </a-table-column>
  </a-table>

  <a-pagination
    style="margin-top: 16px; text-align: right"
    :current="query.page"
    :page-size="query.page_size"
    :total="pagination.total"
    @change="onPageChange"
  />

  <AdminDetailModal v-model:open="detailModal.open" title="用户详情" :loading="detailModal.loading" width="1100px">
    <template v-if="detailModal.data">
      <div style="margin-bottom: 12px; display: flex; gap: 8px; justify-content: flex-end">
        <a-button v-if="showGrantPro" type="primary" @click="openGrant">发放 Pro</a-button>
        <a-button v-if="showRecyclePro" danger @click="openRecycle">回收 Pro</a-button>
      </div>

      <a-descriptions bordered :column="2" size="small">
        <a-descriptions-item label="用户 ID">{{ detailModal.data.user.id }}</a-descriptions-item>
        <a-descriptions-item label="显示名称">{{ detailModal.data.user.display_name || '-' }}</a-descriptions-item>
        <a-descriptions-item label="账号标识">{{ detailModal.data.user.username }}</a-descriptions-item>
        <a-descriptions-item label="邮箱">{{ detailModal.data.user.email || '-' }}</a-descriptions-item>
        <a-descriptions-item label="状态">
          <a-tag :color="detailModal.data.user.is_active ? 'green' : 'red'">
            {{ detailModal.data.user.is_active ? '启用' : '禁用' }}
          </a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="是否 Staff">{{ detailModal.data.user.is_staff ? '是' : '否' }}</a-descriptions-item>
        <a-descriptions-item label="是否 Superuser">{{ detailModal.data.user.is_superuser ? '是' : '否' }}</a-descriptions-item>
        <a-descriptions-item label="Pro 权益" :span="2">
          <a-tag :color="detailModal.data.pro.is_pro ? 'green' : 'default'">
            {{ proSummaryText(detailModal.data.pro) }}
          </a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="注册时间">{{ formatDateTime(detailModal.data.user.date_joined) }}</a-descriptions-item>
        <a-descriptions-item label="最近登录">{{ formatDateTime(detailModal.data.user.last_login) }}</a-descriptions-item>
      </a-descriptions>

      <div style="margin-top: 16px" />
      <a-table
        size="small"
        :data-source="detailModal.data.auth_identities"
        :pagination="false"
        row-key="id"
        :scroll="{ x: 1100 }"
        :title="() => '认证信息'"
      >
        <template #emptyText>
          <a-empty description="暂无绑定认证信息" />
        </template>
        <a-table-column title="认证方式" data-index="provider_label" :width="100" />
        <a-table-column title="身份标识" data-index="provider_uid_masked" :width="220" />
        <a-table-column title="身份域" data-index="bundle_id" :width="180">
          <template #default="{ record }">
            {{ record.bundle_id || '-' }}
          </template>
        </a-table-column>
        <a-table-column title="绑定时间" key="created_at" :width="180">
          <template #default="{ record }">
            {{ formatDateTime(record.created_at) }}
          </template>
        </a-table-column>
        <a-table-column title="更新时间" key="updated_at" :width="180">
          <template #default="{ record }">
            {{ formatDateTime(record.updated_at) }}
          </template>
        </a-table-column>
      </a-table>

      <div style="margin-top: 16px" />
      <a-table
        size="small"
        :data-source="detailModal.data.trusted_devices"
        :pagination="false"
        row-key="id"
        :scroll="{ x: 1900 }"
        :title="() => '登录设备信息'"
      >
        <a-table-column title="ID" data-index="id" :width="70" />
        <a-table-column title="device_id" data-index="device_id" :width="280" />
        <a-table-column title="bundle_id" data-index="bundle_id" :width="180" />
        <a-table-column title="应用版本" key="app_version" :width="100">
          <template #default="{ record }">
            {{ record.app_version || '-' }}
          </template>
        </a-table-column>
        <a-table-column title="构建号" key="build_version" :width="90">
          <template #default="{ record }">
            {{ record.build_version || '-' }}
          </template>
        </a-table-column>
        <a-table-column title="平台" data-index="platform" :width="80" />
        <a-table-column title="系统版本" data-index="system_version" :width="100" />
        <a-table-column title="设备型号" key="device_model" :width="140">
          <template #default="{ record }">
            {{ record.device_model_name || record.device_model || '-' }}
          </template>
        </a-table-column>
        <a-table-column title="设备名称" data-index="device_name" :width="140" />
        <a-table-column title="通知权限" key="notifications_enabled" :width="90">
          <template #default="{ record }">
            {{ record.notifications_enabled ? '已开启' : '未开启' }}
          </template>
        </a-table-column>
        <a-table-column title="push_token" data-index="push_token_masked" :width="160">
          <template #default="{ record }">
            {{ record.push_token_masked || '-' }}
          </template>
        </a-table-column>
        <a-table-column title="国家/地区" key="region" :width="100">
          <template #default="{ record }">
            {{ record.country_code || record.region_code || '-' }}
          </template>
        </a-table-column>
        <a-table-column title="语言" data-index="language_code" :width="70" />
        <a-table-column title="模拟器" key="is_simulator" :width="80">
          <template #default="{ record }">
            {{ record.is_simulator ? '是' : '否' }}
          </template>
        </a-table-column>
        <a-table-column title="是否失效" key="is_revoked" :width="90">
          <template #default="{ record }">
            <a-tag :color="record.is_revoked ? 'red' : 'green'">{{ record.is_revoked ? '失效' : '有效' }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="首次登记" key="first_seen" :width="180">
          <template #default="{ record }">
            {{ formatDateTime(record.first_seen) }}
          </template>
        </a-table-column>
        <a-table-column title="最近上报" key="last_seen" :width="180">
          <template #default="{ record }">
            {{ formatDateTime(record.last_seen) }}
          </template>
        </a-table-column>
        <a-table-column title="request_id" data-index="request_id" :width="280" />
      </a-table>

      <div style="margin-top: 16px" />
      <a-table
        size="small"
        :data-source="detailModal.data.device_sessions"
        :pagination="false"
        row-key="id"
        :scroll="{ x: 1400 }"
        :title="() => '登录会话流水'"
      >
        <a-table-column title="ID" data-index="id" :width="70" />
        <a-table-column title="trusted_device_id" data-index="trusted_device" :width="130" />
        <a-table-column title="device_id" data-index="device_id" :width="280" />
        <a-table-column title="bundle_id" data-index="bundle_id" :width="180" />
        <a-table-column title="状态" key="status" :width="90">
          <template #default="{ record }">
            <a-tag :color="sessionStatusColor(record.status)">{{ sessionStatusLabel(record.status) }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="会话版本" data-index="session_version" :width="90" />
        <a-table-column title="失效原因" key="revoked_reason" :width="160">
          <template #default="{ record }">
            {{ record.revoked_reason || '-' }}
          </template>
        </a-table-column>
        <a-table-column title="替换会话" key="replaced_by" :width="90">
          <template #default="{ record }">
            {{ record.replaced_by ?? '-' }}
          </template>
        </a-table-column>
        <a-table-column title="最近刷新" key="last_refreshed_at" :width="180">
          <template #default="{ record }">
            {{ formatDateTime(record.last_refreshed_at) }}
          </template>
        </a-table-column>
        <a-table-column title="创建时间" key="created_at" :width="180">
          <template #default="{ record }">
            {{ formatDateTime(record.created_at) }}
          </template>
        </a-table-column>
        <a-table-column title="更新时间" key="updated_at" :width="180">
          <template #default="{ record }">
            {{ formatDateTime(record.updated_at) }}
          </template>
        </a-table-column>
      </a-table>
    </template>
  </AdminDetailModal>

  <a-modal v-model:open="grantModal.open" title="发放 Pro 权益" :confirm-loading="grantModal.loading" @ok="submitGrant">
    <a-form layout="vertical">
      <a-form-item label="试用时长">
        <a-radio-group v-model:value="grantModal.preset">
          <a-radio :value="6">6 天</a-radio>
          <a-radio :value="15">15 天</a-radio>
          <a-radio :value="30">30 天</a-radio>
          <a-radio :value="90">90 天</a-radio>
          <a-radio value="custom">自定义</a-radio>
        </a-radio-group>
      </a-form-item>
      <a-form-item v-if="grantModal.preset === 'custom'" label="自定义天数">
        <a-input-number v-model:value="grantModal.customDays" :min="1" :max="3650" style="width: 100%" />
      </a-form-item>
      <a-form-item label="备注">
        <a-textarea v-model:value="grantModal.note" :maxlength="255" show-count placeholder="可选" />
      </a-form-item>
    </a-form>
  </a-modal>

  <a-modal v-model:open="recycleModal.open" title="回收 Pro 权益" :confirm-loading="recycleModal.loading" @ok="submitRecycle">
    <a-form layout="vertical">
      <a-form-item label="备注" required>
        <a-textarea v-model:value="recycleModal.note" :maxlength="255" show-count placeholder="请填写回收原因" />
      </a-form-item>
    </a-form>
  </a-modal>

  <MedicalDataUserOverviewModal
    v-model:open="medicalDetailModal.open"
    :user-id="medicalDetailModal.userId"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message, Modal } from 'ant-design-vue';
import type { Dayjs } from 'dayjs';
import {
  fetchUserDetail,
  fetchUsers,
  grantUserPro,
  recycleUserPro,
  updateUserStatus,
  type AdminUserDetail,
  type AdminUserProSummary,
} from '../api/modules/users';
import { useAuthStore } from '../stores/auth';
import { useTableSort } from '../composables/useTableSort';
import type { AdminUser, Pagination } from '../types';
import AdminDetailModal from '../components/detail/AdminDetailModal.vue';
import MedicalDataUserOverviewModal from '../components/medical/MedicalDataUserOverviewModal.vue';
import TableHoverActions from '../components/TableHoverActions.vue';
import { calcActionsColWidth } from '../utils/tableActionsWidth';
import { formatDateTime } from '../utils/datetime';
import { formatAdminDateTimeRangeValue } from '../utils/dateRange';

const auth = useAuthStore();
const loading = ref(false);
const rows = ref<AdminUser[]>([]);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });

const query = reactive({
  page: 1,
  page_size: 20,
  q: '',
  is_active: '',
  bundle_id: '',
  date_joined_after: '',
  date_joined_before: '',
  last_used_after: '',
  last_used_before: '',
});

const joinedRange = ref<[Dayjs, Dayjs] | null>(null);
const lastUsedRange = ref<[Dayjs, Dayjs] | null>(null);

const detailModal = reactive({
  open: false,
  loading: false,
  data: null as AdminUserDetail | null,
});

const medicalDetailModal = reactive({
  open: false,
  userId: 0,
});

const grantModal = reactive({
  open: false,
  loading: false,
  preset: 15 as number | 'custom',
  customDays: 15,
  note: '',
});

const recycleModal = reactive({
  open: false,
  loading: false,
  note: '',
});

const canUpdate = computed(() => auth.hasPermission('button:user:status:update'));
const canGrantPro = computed(() => auth.hasPermission('button:user:pro:grant'));
const canRecyclePro = computed(() => auth.hasPermission('button:user:pro:recycle'));
const actionsColWidth = computed(() =>
  calcActionsColWidth({
    buttons: 2 + (canUpdate.value ? 1 : 0),
    min: 120,
  }),
);

const showGrantPro = computed(() => {
  if (!canGrantPro.value || !detailModal.data) return false;
  const status = detailModal.data.pro.status;
  return !detailModal.data.pro.is_pro && status !== 'pending';
});

const showRecyclePro = computed(() => {
  return Boolean(canRecyclePro.value && detailModal.data?.pro.is_pro);
});

const { sortQuery, getColumnSortOrder, handleTableChange } = useTableSort({
  defaultSortBy: 'date_joined',
  defaultOrder: 'desc',
  fields: {
    id: { key: 'id', apiField: 'id' },
    date_joined: { key: 'date_joined', apiField: 'date_joined' },
    last_used_at: { key: 'last_used_at', apiField: 'last_used_at' },
  },
  onSortChange: () => {
    query.page = 1;
    load();
  },
});

function proStatusLabel(status: string) {
  switch (status) {
    case 'pending':
      return '审核中';
    case 'active':
      return '生效中';
    case 'rejected':
      return '已拒绝';
    case 'expired':
      return '已过期';
    case 'none':
      return '未开通';
    default:
      return status || '-';
  }
}

function proSummaryText(pro: AdminUserProSummary) {
  if (pro.is_pro) {
    return `Pro · ${proStatusLabel(pro.status)} · 到期 ${formatDateTime(pro.expires_at)}`;
  }
  if (pro.status && pro.status !== 'none') {
    return `非 Pro · ${proStatusLabel(pro.status)}`;
  }
  return '非 Pro';
}

function sessionStatusLabel(status: string) {
  switch (status) {
    case 'active':
      return '有效';
    case 'revoked':
      return '已失效';
    case 'logged_out':
      return '已退出';
    default:
      return status;
  }
}

function sessionStatusColor(status: string) {
  switch (status) {
    case 'active':
      return 'success';
    case 'revoked':
      return 'error';
    case 'logged_out':
      return 'default';
    default:
      return 'default';
  }
}

async function load() {
  try {
    loading.value = true;
    const data = await fetchUsers({
      ...query,
      ...sortQuery.value,
    });
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  query.page = 1;
  load();
}

function onJoinedRangeChange(values: [Dayjs | string, Dayjs | string] | null) {
  query.date_joined_after = formatAdminDateTimeRangeValue(values?.[0]);
  query.date_joined_before = formatAdminDateTimeRangeValue(values?.[1]);
}

function onLastUsedRangeChange(values: [Dayjs | string, Dayjs | string] | null) {
  query.last_used_after = formatAdminDateTimeRangeValue(values?.[0]);
  query.last_used_before = formatAdminDateTimeRangeValue(values?.[1]);
}

function onReset() {
  query.page = 1;
  query.q = '';
  query.is_active = '';
  query.bundle_id = '';
  query.date_joined_after = '';
  query.date_joined_before = '';
  query.last_used_after = '';
  query.last_used_before = '';
  joinedRange.value = null;
  lastUsedRange.value = null;
  load();
}

async function openUserDetail(record: AdminUser) {
  detailModal.open = true;
  detailModal.loading = true;
  detailModal.data = null;
  try {
    detailModal.data = await fetchUserDetail(record.id);
  } catch (error: any) {
    message.error(error?.message || '加载失败');
  } finally {
    detailModal.loading = false;
  }
}

function openMedicalDetail(record: AdminUser) {
  medicalDetailModal.userId = record.id;
  medicalDetailModal.open = true;
}

async function refreshDetailAndList() {
  if (detailModal.data?.user.id) {
    detailModal.data = await fetchUserDetail(detailModal.data.user.id);
  }
  await load();
}

function openGrant() {
  grantModal.open = true;
  grantModal.loading = false;
  grantModal.preset = 15;
  grantModal.customDays = 15;
  grantModal.note = '';
}

async function submitGrant() {
  const userId = detailModal.data?.user.id;
  if (!userId) return;
  const days = grantModal.preset === 'custom' ? Number(grantModal.customDays) : Number(grantModal.preset);
  if (!days || days < 1) {
    message.error('请输入有效天数');
    return;
  }
  grantModal.loading = true;
  try {
    await grantUserPro(userId, { grant_days: days, note: grantModal.note || undefined });
    message.success('已发放 Pro 权益');
    grantModal.open = false;
    await refreshDetailAndList();
  } catch (error: any) {
    message.error(error?.message || '发放失败');
  } finally {
    grantModal.loading = false;
  }
}

function openRecycle() {
  recycleModal.open = true;
  recycleModal.loading = false;
  recycleModal.note = '';
}

async function submitRecycle() {
  const userId = detailModal.data?.user.id;
  if (!userId) return;
  const note = recycleModal.note.trim();
  if (!note) {
    message.error('请填写回收备注');
    return;
  }
  recycleModal.loading = true;
  try {
    await recycleUserPro(userId, { note });
    message.success('已回收 Pro 权益');
    recycleModal.open = false;
    await refreshDetailAndList();
  } catch (error: any) {
    message.error(error?.message || '回收失败');
  } finally {
    recycleModal.loading = false;
  }
}

function onStatusAction(record: AdminUser) {
  if (record.is_active) {
    Modal.confirm({
      title: '禁用用户',
      content: '禁用后该用户将无法继续登录和使用 App，确定要禁用吗？',
      onOk: () => onToggleStatus(record.id, false),
    });
    return;
  }
  void onToggleStatus(record.id, true);
}

async function onToggleStatus(userId: number, isActive: boolean) {
  try {
    await updateUserStatus(userId, isActive);
    message.success('用户状态已更新');
    await load();
  } catch (error: any) {
    message.error(error?.message || '更新失败');
  }
}

function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}

onMounted(load);
</script>
