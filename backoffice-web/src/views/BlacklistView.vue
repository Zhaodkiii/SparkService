<template>
  <a-tabs v-model:activeKey="activeTab" @change="onTabChange">
    <a-tab-pane key="entries" tab="黑名单">
      <a-space wrap style="margin-bottom: 16px">
        <a-input-search
          v-model:value="query.q"
          placeholder="手机号 / 邮箱 / 设备ID / 用户ID / 备注"
          enter-button
          @search="loadEntries"
          style="width: 320px"
        />
        <a-select v-model:value="query.dimension" style="width: 140px" allow-clear placeholder="维度" @change="loadEntries">
          <a-select-option value="">全部维度</a-select-option>
          <a-select-option value="user_id">用户</a-select-option>
          <a-select-option value="phone">手机号</a-select-option>
          <a-select-option value="email">邮箱</a-select-option>
          <a-select-option value="device">设备</a-select-option>
        </a-select>
        <a-select v-model:value="query.active_only" style="width: 140px" @change="loadEntries">
          <a-select-option value="true">仅有效</a-select-option>
          <a-select-option value="">全部</a-select-option>
        </a-select>
        <a-button type="primary" @click="loadEntries">查询</a-button>
        <a-button v-if="canManage" type="primary" danger @click="openCreateModal">添加黑名单</a-button>
      </a-space>

      <a-table :data-source="rows" :pagination="false" row-key="id" :loading="loading" :scroll="{ x: 1500 }">
        <a-table-column title="ID" data-index="id" width="80" />
        <a-table-column title="维度" data-index="dimension" width="100">
          <template #default="{ record }">
            {{ dimensionLabel(record.dimension) }}
          </template>
        </a-table-column>
        <a-table-column title="标识" data-index="display_value" width="200" />
        <a-table-column title="关联用户" key="related_user" width="180">
          <template #default="{ record }">
            <div v-if="record.related_user_id">
              <div>#{{ record.related_user_id }}</div>
              <div style="color: #999; font-size: 12px">{{ record.related_user_display || '-' }}</div>
            </div>
            <span v-else>-</span>
          </template>
        </a-table-column>
        <a-table-column title="状态" key="status" width="90">
          <template #default="{ record }">
            <a-tag :color="record.is_active ? 'red' : 'default'">{{ record.is_active ? '生效中' : '已解封' }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="短信" data-index="sms_status" width="100">
          <template #default="{ record }">
            {{ record.sms_status || '-' }}
          </template>
        </a-table-column>
        <a-table-column title="来源" data-index="source" width="110" />
        <a-table-column title="备注" data-index="reason_note" width="220" ellipsis />
        <a-table-column title="创建时间" key="created_at" width="180">
          <template #default="{ record }">
            {{ formatDateTime(record.created_at) }}
          </template>
        </a-table-column>
        <a-table-column title="操作" key="actions" :width="actionsColWidth" fixed="right">
          <template #default="{ record }">
            <TableHoverActions>
              <a-button
                v-if="canManage && record.is_active"
                size="small"
                danger
                @click="onRevoke(record.id)"
              >
                解封
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
        @change="onEntriesPageChange"
      />
    </a-tab-pane>

    <a-tab-pane key="hits" tab="拦截记录">
      <a-space wrap style="margin-bottom: 16px">
        <a-input-search
          v-model:value="hitQuery.q"
          placeholder="命中值 / 设备ID / IP / request_id"
          enter-button
          @search="loadHits"
          style="width: 320px"
        />
        <a-select v-model:value="hitQuery.action" style="width: 140px" allow-clear placeholder="动作" @change="loadHits">
          <a-select-option value="">全部动作</a-select-option>
          <a-select-option value="login">登录</a-select-option>
          <a-select-option value="register">注册</a-select-option>
          <a-select-option value="otp_request">OTP 请求</a-select-option>
          <a-select-option value="identity_bind">身份绑定</a-select-option>
        </a-select>
        <a-select v-model:value="hitQuery.hit_dimension" style="width: 140px" allow-clear placeholder="命中维度" @change="loadHits">
          <a-select-option value="">全部维度</a-select-option>
          <a-select-option value="user_id">用户</a-select-option>
          <a-select-option value="phone">手机号</a-select-option>
          <a-select-option value="email">邮箱</a-select-option>
          <a-select-option value="device">设备</a-select-option>
        </a-select>
        <a-select v-model:value="hitQuery.provider" style="width: 140px" allow-clear placeholder="登录方式" @change="loadHits">
          <a-select-option value="">全部方式</a-select-option>
          <a-select-option value="password">密码</a-select-option>
          <a-select-option value="phone_otp">手机 OTP</a-select-option>
          <a-select-option value="email_otp">邮箱 OTP</a-select-option>
          <a-select-option value="apple">Apple</a-select-option>
          <a-select-option value="device">设备</a-select-option>
        </a-select>
        <a-input
          v-model:value="hitQuery.deny_entry_id"
          placeholder="条目 ID"
          allow-clear
          style="width: 120px"
          @pressEnter="loadHits"
        />
        <a-button type="primary" @click="loadHits">查询</a-button>
      </a-space>

      <a-table :data-source="hitRows" :pagination="false" row-key="id" :loading="hitLoading" :scroll="{ x: 1800 }">
        <a-table-column title="时间" key="created_at" width="180">
          <template #default="{ record }">
            {{ formatDateTime(record.created_at) }}
          </template>
        </a-table-column>
        <a-table-column title="动作" key="action" width="100">
          <template #default="{ record }">
            {{ actionLabel(record.action) }}
          </template>
        </a-table-column>
        <a-table-column title="命中维度" key="hit_dimension" width="100">
          <template #default="{ record }">
            {{ dimensionLabel(record.hit_dimension) }}
          </template>
        </a-table-column>
        <a-table-column title="命中值" data-index="hit_value" width="200" ellipsis />
        <a-table-column title="条目 ID" data-index="deny_entry_id" width="90">
          <template #default="{ record }">
            {{ record.deny_entry_id ?? '-' }}
          </template>
        </a-table-column>
        <a-table-column title="登录方式" data-index="provider" width="110" />
        <a-table-column title="尝试身份" data-index="attempted_identity" width="200" ellipsis />
        <a-table-column title="设备 ID" data-index="device_id" width="180" ellipsis />
        <a-table-column title="IP" data-index="ip_address" width="140" ellipsis />
        <a-table-column title="request_id" data-index="request_id" width="180" ellipsis />
      </a-table>

      <a-pagination
        style="margin-top: 16px; text-align: right"
        :current="hitQuery.page"
        :page-size="hitQuery.page_size"
        :total="hitPagination.total"
        @change="onHitsPageChange"
      />
    </a-tab-pane>
  </a-tabs>

  <a-modal
    v-model:open="createModal.open"
    title="添加黑名单"
    ok-text="确认添加"
    cancel-text="取消"
    :confirm-loading="createModal.loading"
    @ok="submitCreate"
  >
    <a-alert
      type="warning"
      show-icon
      style="margin-bottom: 16px"
      message="选择用户或输入手机号后，将禁用账号并发送禁登短信（如有绑定手机）。封禁用户会同时拉黑其关联设备，这些设备不能再注册新账号。"
    />
    <a-form layout="vertical">
      <a-form-item label="添加方式">
        <a-radio-group v-model:value="createModal.mode">
          <a-radio value="phone">输入手机号</a-radio>
          <a-radio value="user">选择用户</a-radio>
          <a-radio value="device">输入设备 ID</a-radio>
        </a-radio-group>
      </a-form-item>
      <a-form-item v-if="createModal.mode === 'phone'" label="手机号" required>
        <a-input v-model:value="createModal.phone" placeholder="例如 13800138000 或 +8613800138000" />
      </a-form-item>
      <a-form-item v-else-if="createModal.mode === 'device'" label="设备 ID" required>
        <a-input v-model:value="createModal.deviceId" placeholder="客户端 installation device_id" />
      </a-form-item>
      <a-form-item v-else label="用户" required>
        <a-select
          v-model:value="createModal.userId"
          show-search
          allow-clear
          placeholder="搜索用户名 / 邮箱 / 手机号 / 显示名称"
          :filter-option="false"
          :options="createModal.userOptions"
          :loading="createModal.userSearchLoading"
          @search="searchUsers"
        />
      </a-form-item>
      <a-form-item label="内部备注">
        <a-textarea v-model:value="createModal.reasonNote" :rows="3" placeholder="可选，仅后台可见" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { Modal, message } from 'ant-design-vue';
import {
  createAccessDenyEntry,
  fetchAccessDenyHits,
  fetchAccessDenyList,
  fetchUsers,
  revokeAccessDenyEntry,
  type AdminAccessDenyEntry,
  type AdminAccessDenyHit,
} from '../api/modules/users';
import { useAuthStore } from '../stores/auth';
import type { Pagination } from '../types';
import TableHoverActions from '../components/TableHoverActions.vue';
import { calcActionsColWidth } from '../utils/tableActionsWidth';
import { formatDateTime } from '../utils/datetime';

const auth = useAuthStore();
const activeTab = ref<'entries' | 'hits'>('entries');
const loading = ref(false);
const hitLoading = ref(false);
const rows = ref<AdminAccessDenyEntry[]>([]);
const hitRows = ref<AdminAccessDenyHit[]>([]);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const hitPagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });

const query = reactive({
  page: 1,
  page_size: 20,
  q: '',
  dimension: '',
  active_only: 'true',
});

const hitQuery = reactive({
  page: 1,
  page_size: 20,
  q: '',
  action: '',
  hit_dimension: '',
  provider: '',
  deny_entry_id: '',
});

const createModal = reactive({
  open: false,
  loading: false,
  mode: 'phone' as 'phone' | 'user' | 'device',
  phone: '',
  deviceId: '',
  userId: undefined as number | undefined,
  reasonNote: '',
  userOptions: [] as { label: string; value: number }[],
  userSearchLoading: false,
});

const canManage = computed(() => auth.hasPermission('button:user:blacklist:manage'));
const actionsColWidth = computed(() =>
  calcActionsColWidth({ buttons: canManage.value ? 1 : 0 }),
);

function dimensionLabel(value: string) {
  if (value === 'user_id') return '用户';
  if (value === 'phone') return '手机号';
  if (value === 'email') return '邮箱';
  if (value === 'device') return '设备';
  return value;
}

function actionLabel(value: string) {
  if (value === 'login') return '登录';
  if (value === 'register') return '注册';
  if (value === 'otp_request') return 'OTP 请求';
  if (value === 'identity_bind') return '身份绑定';
  return value;
}

async function loadEntries() {
  loading.value = true;
  try {
    const data = await fetchAccessDenyList({
      page: query.page,
      page_size: query.page_size,
      q: query.q || undefined,
      dimension: query.dimension || undefined,
      active_only: query.active_only || undefined,
    });
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
  } finally {
    loading.value = false;
  }
}

async function loadHits() {
  hitLoading.value = true;
  try {
    const data = await fetchAccessDenyHits({
      page: hitQuery.page,
      page_size: hitQuery.page_size,
      q: hitQuery.q || undefined,
      action: hitQuery.action || undefined,
      hit_dimension: hitQuery.hit_dimension || undefined,
      provider: hitQuery.provider || undefined,
      deny_entry_id: hitQuery.deny_entry_id || undefined,
    });
    hitRows.value = data.items;
    Object.assign(hitPagination, data.pagination);
  } finally {
    hitLoading.value = false;
  }
}

function onTabChange(key: string | number) {
  if (key === 'hits') {
    loadHits();
  } else {
    loadEntries();
  }
}

function onEntriesPageChange(page: number) {
  query.page = page;
  loadEntries();
}

function onHitsPageChange(page: number) {
  hitQuery.page = page;
  loadHits();
}

function openCreateModal() {
  createModal.open = true;
  createModal.mode = 'phone';
  createModal.phone = '';
  createModal.deviceId = '';
  createModal.userId = undefined;
  createModal.reasonNote = '';
  createModal.userOptions = [];
}

async function searchUsers(keyword: string) {
  createModal.userSearchLoading = true;
  try {
    const data = await fetchUsers({ page: 1, page_size: 20, q: keyword || undefined });
    createModal.userOptions = data.items.map((user) => {
      const phonePart = user.phone_number ? ` ${user.phone_number}` : '';
      return {
        value: user.id,
        label: `#${user.id} ${user.display_name || user.username}${phonePart}${user.email ? ` (${user.email})` : ''}`.trim(),
      };
    });
  } finally {
    createModal.userSearchLoading = false;
  }
}

async function submitCreate() {
  if (createModal.mode === 'phone' && !createModal.phone.trim()) {
    message.warning('请输入手机号');
    return;
  }
  if (createModal.mode === 'device' && !createModal.deviceId.trim()) {
    message.warning('请输入设备 ID');
    return;
  }
  if (createModal.mode === 'user' && !createModal.userId) {
    message.warning('请选择用户');
    return;
  }

  createModal.loading = true;
  try {
    const payload =
      createModal.mode === 'phone'
        ? { phone: createModal.phone.trim(), reason_note: createModal.reasonNote.trim() || undefined }
        : createModal.mode === 'device'
          ? { device_id: createModal.deviceId.trim(), reason_note: createModal.reasonNote.trim() || undefined }
          : { user_id: createModal.userId, reason_note: createModal.reasonNote.trim() || undefined };
    const result = await createAccessDenyEntry(payload);
    const smsStatus = (result.result.sms_status as string) || '';
    message.success(smsStatus ? `已添加黑名单，短信状态：${smsStatus}` : '已添加黑名单');
    createModal.open = false;
    await loadEntries();
  } catch {
    message.error('添加黑名单失败');
  } finally {
    createModal.loading = false;
  }
}

function onRevoke(entryId: number) {
  Modal.confirm({
    title: '确认解封该黑名单条目？',
    content: '解封后对应标识可重新登录；若为用户维度且无其他有效封禁，账号将恢复启用。',
    okText: '解封',
    cancelText: '取消',
    onOk: async () => {
      await revokeAccessDenyEntry(entryId);
      message.success('已解封');
      await loadEntries();
    },
  });
}

onMounted(() => {
  loadEntries();
  searchUsers('');
});
</script>
