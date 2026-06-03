<template>
  <a-space style="margin-bottom: 16px">
    <a-input-search v-model:value="query.q" placeholder="用户名/邮箱" enter-button @search="load" style="width: 280px" />
    <a-select v-model:value="query.is_active" style="width: 140px" @change="load">
      <a-select-option value="">全部状态</a-select-option>
      <a-select-option value="true">启用</a-select-option>
      <a-select-option value="false">禁用</a-select-option>
    </a-select>
  </a-space>

  <a-table :data-source="rows" :pagination="false" row-key="id" :loading="loading">
    <a-table-column title="ID" data-index="id" />
    <a-table-column title="用户名" data-index="username" />
    <a-table-column title="邮箱" data-index="email" />
    <a-table-column title="状态" key="status">
      <template #default="{ record }">
        <a-tag :color="record.is_active ? 'green' : 'red'">{{ record.is_active ? '启用' : '禁用' }}</a-tag>
      </template>
    </a-table-column>
    <a-table-column title="操作" key="actions" :width="actionsColWidth">
      <template #default="{ record }">
        <TableHoverActions>
          <a-button size="small" @click="openUserDetail(record)">详细</a-button>
          <a-button v-if="canUpdate" size="small" @click="onToggleStatus(record.id, !record.is_active)">
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

  <AdminDetailModal v-model:open="detailModal.open" title="用户详情" :loading="detailModal.loading">
    <a-descriptions v-if="detailModal.data" bordered :column="2" size="small">
      <a-descriptions-item label="用户 ID">{{ detailModal.data.user.id }}</a-descriptions-item>
      <a-descriptions-item label="用户名">{{ detailModal.data.user.username }}</a-descriptions-item>
      <a-descriptions-item label="邮箱">{{ detailModal.data.user.email || '-' }}</a-descriptions-item>
      <a-descriptions-item label="状态">
        <a-tag :color="detailModal.data.user.is_active ? 'green' : 'red'">
          {{ detailModal.data.user.is_active ? '启用' : '禁用' }}
        </a-tag>
      </a-descriptions-item>
      <a-descriptions-item label="是否 Staff">{{ detailModal.data.user.is_staff ? '是' : '否' }}</a-descriptions-item>
      <a-descriptions-item label="是否 Superuser">{{ detailModal.data.user.is_superuser ? '是' : '否' }}</a-descriptions-item>
      <a-descriptions-item label="注册时间">{{ detailModal.data.user.date_joined || '-' }}</a-descriptions-item>
      <a-descriptions-item label="最近登录">{{ detailModal.data.user.last_login || '-' }}</a-descriptions-item>
    </a-descriptions>

    <div style="margin-top: 16px" />
    <a-table
      size="small"
      :data-source="detailModal.data?.trusted_devices || []"
      :pagination="false"
      row-key="id"
      :scroll="{ x: 1600 }"
      :title="() => '登录设备信息'"
    >
      <a-table-column title="ID" data-index="id" :width="70" />
      <a-table-column title="device_id" data-index="device_id" :width="280" />
      <a-table-column title="bundle_id" data-index="bundle_id" :width="180" />
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
      <a-table-column title="首次登记" data-index="first_seen" :width="180" />
      <a-table-column title="最近上报" data-index="last_seen" :width="180" />
      <a-table-column title="request_id" data-index="request_id" :width="280" />
    </a-table>

    <div style="margin-top: 16px" />
    <a-table
      size="small"
      :data-source="detailModal.data?.device_sessions || []"
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
          {{ record.last_refreshed_at || '-' }}
        </template>
      </a-table-column>
      <a-table-column title="创建时间" data-index="created_at" :width="180" />
      <a-table-column title="更新时间" data-index="updated_at" :width="180" />
    </a-table>
  </AdminDetailModal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message } from 'ant-design-vue';
import { fetchUserDetail, fetchUsers, updateUserStatus, type AdminUserDetail } from '../api/modules/users';
import { useAuthStore } from '../stores/auth';
import type { AdminUser, Pagination } from '../types';
import AdminDetailModal from '../components/detail/AdminDetailModal.vue';
import TableHoverActions from '../components/TableHoverActions.vue';
import { calcActionsColWidth } from '../utils/tableActionsWidth';

const auth = useAuthStore();
const loading = ref(false);
const rows = ref<AdminUser[]>([]);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });

const query = reactive({
  page: 1,
  page_size: 20,
  q: '',
  is_active: '',
});

const detailModal = reactive({
  open: false,
  loading: false,
  data: null as AdminUserDetail | null,
});

const canUpdate = computed(() => auth.hasPermission('button:user:status:update'));
const actionsColWidth = computed(() =>
  calcActionsColWidth({
    buttons: 1 + (canUpdate.value ? 1 : 0),
    min: 60,
  }),
);

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
    const data = await fetchUsers(query);
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
  } finally {
    loading.value = false;
  }
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
