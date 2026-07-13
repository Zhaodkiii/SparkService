<template>
  <div class="page">
    <a-card title="异常与抑制" class="filter-card">
      <a-space wrap>
        <a-input-search v-model:value="filters.q" placeholder="搜索用户、邮箱、抑制指纹、备注" allow-clear style="width: 280px" @search="reload" />
        <a-select v-model:value="filters.channel" placeholder="渠道" allow-clear style="width: 140px" @change="reload">
          <a-select-option value="all">全部渠道</a-select-option>
          <a-select-option value="apns">APNs</a-select-option>
          <a-select-option value="sms">短信</a-select-option>
          <a-select-option value="email">邮箱</a-select-option>
        </a-select>
        <a-select v-model:value="filters.reason" placeholder="原因" allow-clear style="width: 160px" @change="reload">
          <a-select-option value="user_opt_out">用户退订</a-select-option>
          <a-select-option value="hard_bounce">硬退信</a-select-option>
          <a-select-option value="complaint">投诉</a-select-option>
          <a-select-option value="invalid_endpoint">无效地址</a-select-option>
          <a-select-option value="policy">策略抑制</a-select-option>
        </a-select>
        <a-switch v-model:checked="filters.only_active" checked-children="仅生效" un-checked-children="全部" @change="reload" />
        <a-button @click="reload">刷新</a-button>
      </a-space>
    </a-card>

    <a-card>
      <a-table
        :data-source="rows"
        :loading="loading"
        :pagination="paginationConfig"
        row-key="id"
        size="small"
        @change="handleTableChange"
      >
        <a-table-column title="ID" data-index="id" width="80" />
        <a-table-column title="用户" width="160">
          <template #default="{ record }">{{ record.user_name || '-' }}</template>
        </a-table-column>
        <a-table-column title="渠道" data-index="channel" width="110">
          <template #default="{ text }"><a-tag>{{ channelLabel(text) }}</a-tag></template>
        </a-table-column>
        <a-table-column title="原因" data-index="reason" width="130">
          <template #default="{ text }">{{ reasonLabel(text) }}</template>
        </a-table-column>
        <a-table-column title="状态" width="100">
          <template #default="{ record }">
            <a-tag :color="record.is_active ? 'red' : 'default'">{{ record.is_active ? '生效中' : '已解除' }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="备注" data-index="detail" ellipsis />
        <a-table-column title="到期时间" width="180">
          <template #default="{ record }">{{ formatDateTime(record.expires_at) }}</template>
        </a-table-column>
        <a-table-column title="创建时间" width="180">
          <template #default="{ record }">{{ formatDateTime(record.created_at) }}</template>
        </a-table-column>
        <a-table-column title="操作" width="120">
          <template #default="{ record }">
            <a-popconfirm v-if="record.is_active" title="确认解除该抑制规则？" @confirm="releaseRow(record.id)">
              <a-button type="link" size="small">解除</a-button>
            </a-popconfirm>
            <span v-else>-</span>
          </template>
        </a-table-column>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message } from 'ant-design-vue';
import {
  fetchNotificationSuppressions,
  releaseNotificationSuppression,
  type NotificationSuppression,
} from '../api/modules/notifications';

const loading = ref(false);
const rows = ref<NotificationSuppression[]>([]);
const pagination = reactive({ page: 1, page_size: 20, total: 0 });
const filters = reactive<{ q: string; channel: '' | 'apns' | 'email' | 'sms' | 'all'; reason: string; only_active: boolean }>({
  q: '',
  channel: '',
  reason: '',
  only_active: true,
});

const paginationConfig = computed(() => ({
  current: pagination.page,
  pageSize: pagination.page_size,
  total: pagination.total,
  showSizeChanger: true,
}));

function formatDateTime(value?: string | null) {
  if (!value) return '永久';
  return new Date(value).toLocaleString();
}

function channelLabel(value: string) {
  return ({ all: '全部', apns: 'APNs', sms: '短信', email: '邮箱' } as Record<string, string>)[value] || value;
}

function reasonLabel(value: string) {
  return ({
    user_opt_out: '用户退订',
    hard_bounce: '硬退信',
    complaint: '投诉',
    invalid_endpoint: '无效地址',
    policy: '策略抑制',
  } as Record<string, string>)[value] || value;
}

async function load() {
  loading.value = true;
  try {
    const data = await fetchNotificationSuppressions({
      page: pagination.page,
      page_size: pagination.page_size,
      q: filters.q || undefined,
      channel: filters.channel || undefined,
      reason: filters.reason || undefined,
      only_active: filters.only_active,
    });
    rows.value = data.items;
    pagination.total = data.pagination.total;
  } finally {
    loading.value = false;
  }
}

function reload() {
  pagination.page = 1;
  void load();
}

function handleTableChange(next: { current?: number; pageSize?: number }) {
  pagination.page = next.current || 1;
  pagination.page_size = next.pageSize || 20;
  void load();
}

async function releaseRow(id: number) {
  await releaseNotificationSuppression(id);
  message.success('已解除抑制');
  await load();
}

onMounted(load);
</script>

<style scoped>
.page {
  display: grid;
  gap: 16px;
}
.filter-card {
  background: #fafafa;
}
</style>
